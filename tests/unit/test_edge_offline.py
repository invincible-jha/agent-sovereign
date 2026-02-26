"""Tests for OfflineManager, OfflineCapability, CachedResponse."""
from __future__ import annotations

import datetime
from unittest.mock import patch, MagicMock

import pytest

from agent_sovereign.edge.offline import (
    CachedResponse,
    OfflineCapability,
    OfflineManager,
    OfflineStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def capability() -> OfflineCapability:
    return OfflineCapability(
        can_serve_cached_responses=True,
        can_run_local_inference=True,
        can_queue_writes=True,
        max_offline_duration_hours=24,
        cache_ttl_hours=1,
    )


@pytest.fixture()
def manager(capability: OfflineCapability) -> OfflineManager:
    return OfflineManager(capability)


# ---------------------------------------------------------------------------
# OfflineCapability
# ---------------------------------------------------------------------------

class TestOfflineCapability:
    def test_fields(self, capability: OfflineCapability) -> None:
        assert capability.can_serve_cached_responses is True
        assert capability.max_offline_duration_hours == 24
        assert capability.cache_ttl_hours == 1

    def test_default_operations_empty(self) -> None:
        cap = OfflineCapability(
            can_serve_cached_responses=False,
            can_run_local_inference=False,
            can_queue_writes=False,
        )
        assert cap.supported_degraded_operations == []


# ---------------------------------------------------------------------------
# CachedResponse
# ---------------------------------------------------------------------------

class TestCachedResponse:
    def test_not_expired_fresh(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry = CachedResponse(
            cache_key="key",
            response_data="data",
            cached_at=now,
            ttl_hours=1,
        )
        assert not entry.is_expired()

    def test_expired_old_entry(self) -> None:
        past = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2)
        ).isoformat()
        entry = CachedResponse(
            cache_key="key",
            response_data="data",
            cached_at=past,
            ttl_hours=1,
        )
        assert entry.is_expired()

    def test_naive_datetime_treated_as_utc(self) -> None:
        past = (
            datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        ).isoformat()
        entry = CachedResponse(
            cache_key="k",
            response_data="d",
            cached_at=past,
            ttl_hours=1,
        )
        assert entry.is_expired()

    def test_default_cached_at_set(self) -> None:
        entry = CachedResponse(cache_key="k", response_data="d")
        assert entry.cached_at is not None

    def test_hit_count_starts_zero(self) -> None:
        entry = CachedResponse(cache_key="k", response_data="d")
        assert entry.hit_count == 0


# ---------------------------------------------------------------------------
# OfflineManager properties
# ---------------------------------------------------------------------------

class TestOfflineManagerProperties:
    def test_initial_status_online(self, manager: OfflineManager) -> None:
        assert manager.status == OfflineStatus.ONLINE

    def test_capability_accessible(
        self, manager: OfflineManager, capability: OfflineCapability
    ) -> None:
        assert manager.capability is capability


# ---------------------------------------------------------------------------
# OfflineManager.enter_offline_mode / exit_offline_mode
# ---------------------------------------------------------------------------

class TestOfflineModeTransitions:
    def test_enter_offline_mode(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        assert manager.status == OfflineStatus.OFFLINE

    def test_enter_sets_offline_since(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        assert manager._offline_since is not None

    def test_enter_twice_preserves_offline_since(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        first = manager._offline_since
        manager.enter_offline_mode()
        assert manager._offline_since == first

    def test_exit_offline_mode(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        manager.exit_offline_mode()
        assert manager.status == OfflineStatus.ONLINE
        assert manager._offline_since is None


# ---------------------------------------------------------------------------
# OfflineManager.is_online
# ---------------------------------------------------------------------------

class TestIsOnline:
    def test_is_online_success(self, manager: OfflineManager) -> None:
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            result = manager.is_online()
        assert result is True
        assert manager.status == OfflineStatus.ONLINE

    def test_is_online_transitions_back_from_offline(
        self, manager: OfflineManager
    ) -> None:
        manager.enter_offline_mode()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            result = manager.is_online()
        assert result is True
        assert manager.status == OfflineStatus.ONLINE
        assert manager._offline_since is None

    def test_is_online_failure(self, manager: OfflineManager) -> None:
        with patch("socket.create_connection", side_effect=OSError("no route")):
            result = manager.is_online()
        assert result is False
        assert manager.status == OfflineStatus.OFFLINE

    def test_is_online_failure_sets_offline_since(self, manager: OfflineManager) -> None:
        with patch("socket.create_connection", side_effect=OSError("no route")):
            manager.is_online()
        assert manager._offline_since is not None


# ---------------------------------------------------------------------------
# OfflineManager.get_offline_duration
# ---------------------------------------------------------------------------

class TestOfflineDuration:
    def test_online_returns_none(self, manager: OfflineManager) -> None:
        assert manager.get_offline_duration() is None

    def test_offline_returns_timedelta(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        duration = manager.get_offline_duration()
        assert duration is not None
        assert duration.total_seconds() >= 0

    def test_naive_offline_since_handled(self, manager: OfflineManager) -> None:
        manager._offline_since = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
        duration = manager.get_offline_duration()
        assert duration is not None


# ---------------------------------------------------------------------------
# OfflineManager.is_offline_duration_exceeded
# ---------------------------------------------------------------------------

class TestOfflineDurationExceeded:
    def test_online_not_exceeded(self, manager: OfflineManager) -> None:
        assert not manager.is_offline_duration_exceeded()

    def test_indefinite_never_exceeded(self) -> None:
        cap = OfflineCapability(
            can_serve_cached_responses=True,
            can_run_local_inference=False,
            can_queue_writes=False,
            max_offline_duration_hours=-1,
        )
        mgr = OfflineManager(cap)
        mgr.enter_offline_mode()
        mgr._offline_since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=9999)
        assert not mgr.is_offline_duration_exceeded()

    def test_exceeded_when_past_limit(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        manager._offline_since = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
        )
        assert manager.is_offline_duration_exceeded()

    def test_not_exceeded_within_limit(self, manager: OfflineManager) -> None:
        manager.enter_offline_mode()
        manager._offline_since = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        )
        assert not manager.is_offline_duration_exceeded()


# ---------------------------------------------------------------------------
# OfflineManager.cache_response / get_cached_response
# ---------------------------------------------------------------------------

class TestCacheOperations:
    def test_cache_and_retrieve(self, manager: OfflineManager) -> None:
        key = manager.cache_response("prompt-1", "response-1")
        assert key is not None
        entry = manager.get_cached_response("prompt-1")
        assert entry is not None
        assert entry.response_data == "response-1"

    def test_hit_count_increments(self, manager: OfflineManager) -> None:
        manager.cache_response("p2", "r2")
        manager.get_cached_response("p2")
        entry = manager.get_cached_response("p2")
        assert entry is not None
        assert entry.hit_count == 2

    def test_missing_key_returns_none(self, manager: OfflineManager) -> None:
        assert manager.get_cached_response("nonexistent") is None

    def test_expired_entry_evicted_on_get(self, manager: OfflineManager) -> None:
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).isoformat()
        cache_key = OfflineManager._compute_cache_key("expired-req")
        manager._cache[cache_key] = CachedResponse(
            cache_key=cache_key,
            response_data="old",
            cached_at=past,
            ttl_hours=1,
        )
        assert manager.get_cached_response("expired-req") is None

    def test_cannot_serve_cached_returns_none(self) -> None:
        cap = OfflineCapability(
            can_serve_cached_responses=False,
            can_run_local_inference=False,
            can_queue_writes=False,
        )
        mgr = OfflineManager(cap)
        mgr.cache_response("req", "resp")
        assert mgr.get_cached_response("req") is None

    def test_cache_key_is_deterministic(self) -> None:
        k1 = OfflineManager._compute_cache_key("same-input")
        k2 = OfflineManager._compute_cache_key("same-input")
        assert k1 == k2

    def test_different_inputs_different_keys(self) -> None:
        k1 = OfflineManager._compute_cache_key("input-a")
        k2 = OfflineManager._compute_cache_key("input-b")
        assert k1 != k2


# ---------------------------------------------------------------------------
# OfflineManager.evict_expired_cache / get_cache_stats
# ---------------------------------------------------------------------------

class TestCacheEviction:
    def test_evict_expired(self, manager: OfflineManager) -> None:
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        ).isoformat()
        for i in range(3):
            key = OfflineManager._compute_cache_key(f"old-{i}")
            manager._cache[key] = CachedResponse(
                cache_key=key,
                response_data="old",
                cached_at=past,
                ttl_hours=1,
            )
        manager.cache_response("fresh", "data")
        evicted = manager.evict_expired_cache()
        assert evicted == 3
        assert len(manager._cache) == 1

    def test_evict_none_expired(self, manager: OfflineManager) -> None:
        manager.cache_response("current", "data")
        evicted = manager.evict_expired_cache()
        assert evicted == 0

    def test_get_cache_stats_empty(self, manager: OfflineManager) -> None:
        stats = manager.get_cache_stats()
        assert stats["total_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["total_hits"] == 0

    def test_get_cache_stats_with_entries(self, manager: OfflineManager) -> None:
        manager.cache_response("s1", "d1")
        manager.cache_response("s2", "d2")
        manager.get_cached_response("s1")
        stats = manager.get_cache_stats()
        assert stats["total_entries"] == 2
        assert stats["total_hits"] == 1
