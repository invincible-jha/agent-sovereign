"""Offline mode manager for edge deployments.

Manages the transition between online and offline operation, cached response
serving, and graceful degradation when network connectivity is unavailable.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import socket
from dataclasses import dataclass, field
from enum import Enum


class OfflineStatus(str, Enum):
    """Current connectivity status of the edge node."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"  # Partial connectivity


@dataclass
class OfflineCapability:
    """Describes the offline operation capabilities of an edge deployment.

    Attributes
    ----------
    can_serve_cached_responses:
        Whether the node can return cached responses when offline.
    can_run_local_inference:
        Whether local model inference is available without network.
    can_queue_writes:
        Whether write operations can be queued for later sync.
    max_offline_duration_hours:
        Maximum hours the node should operate offline before requiring
        re-synchronisation. -1 means indefinite.
    cache_ttl_hours:
        Time-to-live for cached responses in hours.
    supported_degraded_operations:
        List of operation types available in degraded/offline mode.
    """

    can_serve_cached_responses: bool
    can_run_local_inference: bool
    can_queue_writes: bool
    max_offline_duration_hours: int = 24
    cache_ttl_hours: int = 1
    supported_degraded_operations: list[str] = field(default_factory=list)


@dataclass
class CachedResponse:
    """A cached response entry.

    Attributes
    ----------
    cache_key:
        Deterministic key identifying this cached entry.
    response_data:
        The serialised response payload.
    cached_at:
        ISO-8601 UTC timestamp of when this response was cached.
    ttl_hours:
        Number of hours this entry remains valid.
    hit_count:
        Number of times this entry has been served from cache.
    """

    cache_key: str
    response_data: str
    cached_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    ttl_hours: int = 1
    hit_count: int = 0

    def is_expired(self) -> bool:
        """Return True if this cache entry has exceeded its TTL.

        Returns
        -------
        bool
            True when the cached_at timestamp plus ttl_hours is in the past.
        """
        cached = datetime.datetime.fromisoformat(self.cached_at)
        if cached.tzinfo is None:
            cached = cached.replace(tzinfo=datetime.timezone.utc)
        expiry = cached + datetime.timedelta(hours=self.ttl_hours)
        return datetime.datetime.now(datetime.timezone.utc) > expiry


class OfflineManager:
    """Manages offline mode transitions and cached response serving.

    Parameters
    ----------
    capability:
        The OfflineCapability describing what this node can do offline.
    connectivity_check_host:
        Hostname to ping for connectivity checking (default: "8.8.8.8").
    connectivity_check_port:
        Port to use for connectivity checking (default: 53).
    connectivity_check_timeout_seconds:
        Timeout in seconds for each connectivity check (default: 2).
    """

    def __init__(
        self,
        capability: OfflineCapability,
        connectivity_check_host: str = "8.8.8.8",
        connectivity_check_port: int = 53,
        connectivity_check_timeout_seconds: float = 2.0,
    ) -> None:
        self._capability = capability
        self._check_host = connectivity_check_host
        self._check_port = connectivity_check_port
        self._check_timeout = connectivity_check_timeout_seconds
        self._status: OfflineStatus = OfflineStatus.ONLINE
        self._offline_since: datetime.datetime | None = None
        self._cache: dict[str, CachedResponse] = {}

    @property
    def capability(self) -> OfflineCapability:
        """Return the offline capability descriptor."""
        return self._capability

    @property
    def status(self) -> OfflineStatus:
        """Return the current offline status."""
        return self._status

    def is_online(self) -> bool:
        """Check live network connectivity and update internal status.

        Attempts a TCP connection to the configured host/port. Updates
        ``status`` based on the result.

        Returns
        -------
        bool
            True if the node can reach the configured endpoint.
        """
        try:
            with socket.create_connection(
                (self._check_host, self._check_port),
                timeout=self._check_timeout,
            ):
                if self._status == OfflineStatus.OFFLINE:
                    self._status = OfflineStatus.ONLINE
                    self._offline_since = None
                return True
        except OSError:
            if self._status == OfflineStatus.ONLINE:
                self._status = OfflineStatus.OFFLINE
                self._offline_since = datetime.datetime.now(datetime.timezone.utc)
            return False

    def enter_offline_mode(self) -> None:
        """Manually transition the node into offline mode.

        Use this when the connectivity check is not sufficient or when
        a deliberate offline transition is required (e.g. entering an
        air-gapped environment).
        """
        self._status = OfflineStatus.OFFLINE
        if self._offline_since is None:
            self._offline_since = datetime.datetime.now(datetime.timezone.utc)

    def exit_offline_mode(self) -> None:
        """Manually transition the node back to online mode.

        Use this after restoring connectivity, before re-enabling sync
        operations.
        """
        self._status = OfflineStatus.ONLINE
        self._offline_since = None

    def get_offline_duration(self) -> datetime.timedelta | None:
        """Return how long the node has been offline, or None if online.

        Returns
        -------
        datetime.timedelta | None
            Duration since the node entered offline mode, or None if
            currently online.
        """
        if self._offline_since is None:
            return None
        now = datetime.datetime.now(datetime.timezone.utc)
        if self._offline_since.tzinfo is None:
            offline_since = self._offline_since.replace(tzinfo=datetime.timezone.utc)
        else:
            offline_since = self._offline_since
        return now - offline_since

    def is_offline_duration_exceeded(self) -> bool:
        """Return True if the node has been offline beyond the configured limit.

        Returns
        -------
        bool
            True when offline duration exceeds ``capability.max_offline_duration_hours``
            and that limit is not set to -1 (indefinite).
        """
        max_hours = self._capability.max_offline_duration_hours
        if max_hours == -1:
            return False
        duration = self.get_offline_duration()
        if duration is None:
            return False
        return duration.total_seconds() > max_hours * 3600

    def cache_response(self, request_key: str, response_data: str) -> str:
        """Store a response in the local cache.

        Parameters
        ----------
        request_key:
            A string that uniquely identifies the request (e.g. a prompt hash).
        response_data:
            The serialised response to cache.

        Returns
        -------
        str
            The cache key used to store the entry.
        """
        cache_key = self._compute_cache_key(request_key)
        self._cache[cache_key] = CachedResponse(
            cache_key=cache_key,
            response_data=response_data,
            ttl_hours=self._capability.cache_ttl_hours,
        )
        return cache_key

    def get_cached_response(self, request_key: str) -> CachedResponse | None:
        """Retrieve a cached response for a request key.

        Expired entries are evicted and None is returned.

        Parameters
        ----------
        request_key:
            The same key string used when ``cache_response`` was called.

        Returns
        -------
        CachedResponse | None
            The cached entry if present and not expired, otherwise None.
        """
        if not self._capability.can_serve_cached_responses:
            return None

        cache_key = self._compute_cache_key(request_key)
        entry = self._cache.get(cache_key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[cache_key]
            return None
        entry.hit_count += 1
        return entry

    def evict_expired_cache(self) -> int:
        """Remove all expired entries from the response cache.

        Returns
        -------
        int
            Number of entries evicted.
        """
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def get_cache_stats(self) -> dict[str, int]:
        """Return basic statistics about the response cache.

        Returns
        -------
        dict[str, int]
            Keys: "total_entries", "expired_entries", "total_hits".
        """
        expired = sum(1 for e in self._cache.values() if e.is_expired())
        total_hits = sum(e.hit_count for e in self._cache.values())
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired,
            "total_hits": total_hits,
        }

    @staticmethod
    def _compute_cache_key(request_key: str) -> str:
        """Compute a deterministic cache key from a request string.

        Parameters
        ----------
        request_key:
            The raw request identifier.

        Returns
        -------
        str
            SHA-256 hex digest of the request key.
        """
        return hashlib.sha256(request_key.encode("utf-8")).hexdigest()


__all__ = [
    "CachedResponse",
    "OfflineCapability",
    "OfflineManager",
    "OfflineStatus",
]
