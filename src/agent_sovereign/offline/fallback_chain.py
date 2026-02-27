"""Offline-first tool fallback chain.

Implements a four-tier fallback strategy for tool calls when network
connectivity is unavailable:

1. **Primary**  — Call the live online API as normal.
2. **Cached**   — Return the last known good response from the cache.
3. **Local**    — Execute an offline-capable alternative implementation.
4. **Queued**   — Persist the call and retry it once the network returns.

The :class:`OfflineFallbackChain` tracks online/offline state and selects
the appropriate tier automatically on each invocation.
"""
from __future__ import annotations

import datetime
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class OnlineState(str, Enum):
    """Connectivity state of the fallback chain."""

    ONLINE = "online"
    OFFLINE = "offline"


class FallbackOutcome(str, Enum):
    """Which fallback tier served the tool call."""

    PRIMARY = "primary"
    CACHED = "cached"
    LOCAL = "local"
    QUEUED = "queued"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FallbackStrategy:
    """Per-tool fallback configuration.

    Attributes
    ----------
    tool_name:
        Identifier for the tool this strategy applies to.
    enable_cache:
        Whether to attempt the cached-response tier.
    enable_local:
        Whether to attempt the local-alternative tier.
    enable_queue:
        Whether to queue calls when all other tiers fail.
    cache_ttl_seconds:
        How long a cached response remains valid.
    max_queue_size:
        Maximum number of queued calls retained per tool.
    """

    tool_name: str
    enable_cache: bool = True
    enable_local: bool = False
    enable_queue: bool = True
    cache_ttl_seconds: int = 3600
    max_queue_size: int = 100


@dataclass
class QueuedCall:
    """A deferred tool call waiting to be retried.

    Attributes
    ----------
    tool_name:
        Name of the tool to invoke.
    args:
        Positional arguments for the deferred call.
    kwargs:
        Keyword arguments for the deferred call.
    queued_at:
        UTC timestamp when the call was queued.
    """

    tool_name: str
    args: list[object]
    kwargs: dict[str, object]
    queued_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


@dataclass(frozen=True)
class FallbackResult:
    """Result returned after the fallback chain executes.

    Attributes
    ----------
    outcome:
        Which tier served the call.
    value:
        The return value from the successful tier, or None if queued/failed.
    tool_name:
        The tool that was invoked.
    served_at:
        UTC timestamp of when the result was produced.
    cache_age_seconds:
        Age of the cached entry in seconds, or None when not from cache.
    error:
        Error message when outcome is FAILED.
    """

    outcome: FallbackOutcome
    value: object
    tool_name: str
    served_at: datetime.datetime
    cache_age_seconds: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    """Internal cache entry for a tool response."""

    value: object
    stored_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    ttl_seconds: int = 3600

    def is_expired(self) -> bool:
        """Return True if this entry has exceeded its TTL."""
        now = datetime.datetime.now(datetime.timezone.utc)
        age = (now - self.stored_at).total_seconds()
        return age > self.ttl_seconds

    def age_seconds(self) -> float:
        """Return the age of this entry in seconds."""
        now = datetime.datetime.now(datetime.timezone.utc)
        return (now - self.stored_at).total_seconds()


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


class OfflineFallbackChain:
    """Per-tool offline fallback chain.

    Manages state for multiple tools, each with its own
    :class:`FallbackStrategy`.  When a tool call is made:

    - If **online**: attempt the primary callable.  On success, update cache.
    - If **offline** or primary fails: cascade through cache → local → queue.

    Parameters
    ----------
    initial_state:
        Starting connectivity state (default ONLINE).

    Example
    -------
    ::

        chain = OfflineFallbackChain()
        chain.register_tool(
            strategy=FallbackStrategy("weather_api", enable_local=True),
            primary=fetch_weather,
            local_alt=cached_weather_stub,
        )
        chain.set_state(OnlineState.OFFLINE)
        result = chain.call("weather_api", "London")
    """

    def __init__(self, initial_state: OnlineState = OnlineState.ONLINE) -> None:
        self._state: OnlineState = initial_state
        self._strategies: dict[str, FallbackStrategy] = {}
        self._primaries: dict[str, Callable[...]] = {}
        self._locals: dict[str, Callable[...]] = {}
        self._caches: dict[str, dict[str, _CacheEntry]] = {}
        self._queues: dict[str, deque[QueuedCall]] = {}
        self._call_counts: dict[str, dict[FallbackOutcome, int]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_tool(
        self,
        strategy: FallbackStrategy,
        primary: Callable[...],
        local_alt: Callable[...] | None = None,
    ) -> None:
        """Register a tool with its fallback strategy.

        Parameters
        ----------
        strategy:
            The :class:`FallbackStrategy` for this tool.
        primary:
            Callable for the online API call.
        local_alt:
            Optional offline-capable alternative callable.
        """
        name = strategy.tool_name
        self._strategies[name] = strategy
        self._primaries[name] = primary
        if local_alt is not None:
            self._locals[name] = local_alt
        self._caches[name] = {}
        self._queues[name] = deque(maxlen=strategy.max_queue_size)
        self._call_counts[name] = {outcome: 0 for outcome in FallbackOutcome}

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state(self, state: OnlineState) -> None:
        """Manually set the connectivity state.

        Parameters
        ----------
        state:
            The new :class:`OnlineState`.
        """
        if self._state != state:
            logger.info("OfflineFallbackChain state: %s -> %s", self._state, state)
        self._state = state

    @property
    def state(self) -> OnlineState:
        """Return the current connectivity state."""
        return self._state

    def is_online(self) -> bool:
        """Return True when connectivity state is ONLINE."""
        return self._state == OnlineState.ONLINE

    # ------------------------------------------------------------------
    # Tool call entry point
    # ------------------------------------------------------------------

    def call(self, tool_name: str, *args: object, **kwargs: object) -> FallbackResult:
        """Execute a tool call, applying fallback tiers as needed.

        Parameters
        ----------
        tool_name:
            The registered tool name to invoke.
        *args:
            Positional arguments forwarded to the callable.
        **kwargs:
            Keyword arguments forwarded to the callable.

        Returns
        -------
        FallbackResult
            The result including which tier served the call.

        Raises
        ------
        KeyError
            If *tool_name* has not been registered.
        """
        if tool_name not in self._strategies:
            raise KeyError(f"Tool '{tool_name}' is not registered with OfflineFallbackChain")

        strategy = self._strategies[tool_name]
        cache_key = self._make_cache_key(args, kwargs)

        if self._state == OnlineState.ONLINE:
            result = self._try_primary(tool_name, strategy, cache_key, args, kwargs)
            if result is not None:
                return result

        # Offline or primary failed — cascade
        if strategy.enable_cache:
            result = self._try_cache(tool_name, cache_key)
            if result is not None:
                return result

        if strategy.enable_local and tool_name in self._locals:
            result = self._try_local(tool_name, args, kwargs)
            if result is not None:
                return result

        if strategy.enable_queue:
            return self._queue_call(tool_name, strategy, args, kwargs)

        return self._failed_result(tool_name, "All fallback tiers exhausted")

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def flush_queue(self, tool_name: str) -> list[FallbackResult]:
        """Retry all queued calls for *tool_name* (requires ONLINE state).

        Parameters
        ----------
        tool_name:
            The registered tool whose queue to flush.

        Returns
        -------
        list[FallbackResult]
            Results from each retried queued call.
        """
        if tool_name not in self._queues:
            return []
        results: list[FallbackResult] = []
        queue = self._queues[tool_name]
        retry_calls: list[QueuedCall] = []
        while queue:
            retry_calls.append(queue.popleft())

        for queued in retry_calls:
            res = self.call(tool_name, *queued.args, **queued.kwargs)
            results.append(res)
        return results

    def get_queue_size(self, tool_name: str) -> int:
        """Return the number of queued calls for *tool_name*.

        Parameters
        ----------
        tool_name:
            Registered tool name.

        Returns
        -------
        int
            Number of pending queued calls.
        """
        return len(self._queues.get(tool_name, []))

    def get_call_stats(self, tool_name: str) -> dict[str, int]:
        """Return call outcome statistics for *tool_name*.

        Parameters
        ----------
        tool_name:
            Registered tool name.

        Returns
        -------
        dict[str, int]
            Mapping of outcome name to invocation count.
        """
        counts = self._call_counts.get(tool_name, {})
        return {outcome.value: count for outcome, count in counts.items()}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_primary(
        self,
        tool_name: str,
        strategy: FallbackStrategy,
        cache_key: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> FallbackResult | None:
        """Attempt the primary online callable."""
        try:
            value = self._primaries[tool_name](*args, **kwargs)
            # Update cache on success
            if strategy.enable_cache:
                self._caches[tool_name][cache_key] = _CacheEntry(
                    value=value,
                    ttl_seconds=strategy.cache_ttl_seconds,
                )
            self._increment(tool_name, FallbackOutcome.PRIMARY)
            return FallbackResult(
                outcome=FallbackOutcome.PRIMARY,
                value=value,
                tool_name=tool_name,
                served_at=datetime.datetime.now(datetime.timezone.utc),
            )
        except Exception as exc:
            logger.warning("Primary call for '%s' failed: %s", tool_name, exc)
            return None

    def _try_cache(self, tool_name: str, cache_key: str) -> FallbackResult | None:
        """Attempt to serve from the response cache."""
        cache = self._caches.get(tool_name, {})
        entry = cache.get(cache_key)
        if entry is None or entry.is_expired():
            if entry is not None and entry.is_expired():
                del cache[cache_key]
            return None
        self._increment(tool_name, FallbackOutcome.CACHED)
        return FallbackResult(
            outcome=FallbackOutcome.CACHED,
            value=entry.value,
            tool_name=tool_name,
            served_at=datetime.datetime.now(datetime.timezone.utc),
            cache_age_seconds=entry.age_seconds(),
        )

    def _try_local(
        self,
        tool_name: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> FallbackResult | None:
        """Attempt the local offline-capable alternative."""
        try:
            value = self._locals[tool_name](*args, **kwargs)
            self._increment(tool_name, FallbackOutcome.LOCAL)
            return FallbackResult(
                outcome=FallbackOutcome.LOCAL,
                value=value,
                tool_name=tool_name,
                served_at=datetime.datetime.now(datetime.timezone.utc),
            )
        except Exception as exc:
            logger.warning("Local fallback for '%s' failed: %s", tool_name, exc)
            return None

    def _queue_call(
        self,
        tool_name: str,
        strategy: FallbackStrategy,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> FallbackResult:
        """Queue the call for later retry."""
        queued = QueuedCall(
            tool_name=tool_name,
            args=list(args),
            kwargs=dict(kwargs),
        )
        queue = self._queues[tool_name]
        queue.append(queued)
        self._increment(tool_name, FallbackOutcome.QUEUED)
        logger.info("Queued call for '%s' (queue size=%d)", tool_name, len(queue))
        return FallbackResult(
            outcome=FallbackOutcome.QUEUED,
            value=None,
            tool_name=tool_name,
            served_at=datetime.datetime.now(datetime.timezone.utc),
        )

    def _failed_result(self, tool_name: str, error: str) -> FallbackResult:
        """Return a FAILED outcome."""
        self._increment(tool_name, FallbackOutcome.FAILED)
        return FallbackResult(
            outcome=FallbackOutcome.FAILED,
            value=None,
            tool_name=tool_name,
            served_at=datetime.datetime.now(datetime.timezone.utc),
            error=error,
        )

    def _increment(self, tool_name: str, outcome: FallbackOutcome) -> None:
        """Increment the call counter for *outcome*."""
        if tool_name in self._call_counts:
            self._call_counts[tool_name][outcome] = (
                self._call_counts[tool_name].get(outcome, 0) + 1
            )

    @staticmethod
    def _make_cache_key(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
        """Create a simple cache key from call arguments."""
        return str((args, sorted(kwargs.items())))


__all__ = [
    "FallbackOutcome",
    "FallbackResult",
    "FallbackStrategy",
    "OfflineFallbackChain",
    "OnlineState",
    "QueuedCall",
]
