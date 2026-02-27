"""Tests for agent_sovereign.offline.fallback_chain."""
from __future__ import annotations

import pytest

from agent_sovereign.offline.fallback_chain import (
    FallbackOutcome,
    FallbackResult,
    FallbackStrategy,
    OfflineFallbackChain,
    OnlineState,
    QueuedCall,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_primary(return_value: str = "primary_response") -> object:
    call_count = [0]

    def primary(*args: object, **kwargs: object) -> str:
        call_count[0] += 1
        return return_value

    primary.call_count = call_count  # type: ignore[attr-defined]
    return primary


def _failing_primary(*args: object, **kwargs: object) -> str:
    raise RuntimeError("network unavailable")


def _local_alt(*args: object, **kwargs: object) -> str:
    return "local_response"


@pytest.fixture()
def online_chain() -> OfflineFallbackChain:
    chain = OfflineFallbackChain(initial_state=OnlineState.ONLINE)
    strategy = FallbackStrategy(
        tool_name="test_tool",
        enable_cache=True,
        enable_local=True,
        enable_queue=True,
        cache_ttl_seconds=3600,
    )
    chain.register_tool(strategy, primary=_make_primary(), local_alt=_local_alt)
    return chain


@pytest.fixture()
def offline_chain() -> OfflineFallbackChain:
    chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
    strategy = FallbackStrategy(
        tool_name="test_tool",
        enable_cache=True,
        enable_local=True,
        enable_queue=True,
        cache_ttl_seconds=3600,
    )
    chain.register_tool(strategy, primary=_make_primary(), local_alt=_local_alt)
    return chain


# ---------------------------------------------------------------------------
# State management tests
# ---------------------------------------------------------------------------


class TestOnlineState:
    def test_default_state_is_online(self) -> None:
        chain = OfflineFallbackChain()
        assert chain.state == OnlineState.ONLINE
        assert chain.is_online() is True

    def test_set_offline(self) -> None:
        chain = OfflineFallbackChain()
        chain.set_state(OnlineState.OFFLINE)
        assert chain.state == OnlineState.OFFLINE
        assert chain.is_online() is False

    def test_set_online_after_offline(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        chain.set_state(OnlineState.ONLINE)
        assert chain.is_online() is True

    def test_initial_offline_state(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        assert chain.state == OnlineState.OFFLINE


# ---------------------------------------------------------------------------
# Primary tier tests
# ---------------------------------------------------------------------------


class TestPrimaryTier:
    def test_online_uses_primary(self, online_chain: OfflineFallbackChain) -> None:
        result = online_chain.call("test_tool", "arg1")
        assert result.outcome == FallbackOutcome.PRIMARY
        assert result.value == "primary_response"

    def test_primary_populates_cache(self, online_chain: OfflineFallbackChain) -> None:
        online_chain.call("test_tool", "arg1")
        # Simulate going offline — cache should serve
        online_chain.set_state(OnlineState.OFFLINE)
        result = online_chain.call("test_tool", "arg1")
        assert result.outcome == FallbackOutcome.CACHED

    def test_primary_failure_cascades(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.ONLINE)
        strategy = FallbackStrategy(
            "failing_tool", enable_cache=True, enable_local=True, enable_queue=True
        )
        chain.register_tool(strategy, primary=_failing_primary, local_alt=_local_alt)
        result = chain.call("failing_tool")
        # Should fall through to local
        assert result.outcome == FallbackOutcome.LOCAL

    def test_unregistered_tool_raises(self, online_chain: OfflineFallbackChain) -> None:
        with pytest.raises(KeyError, match="not registered"):
            online_chain.call("nonexistent_tool")


# ---------------------------------------------------------------------------
# Cache tier tests
# ---------------------------------------------------------------------------


class TestCacheTier:
    def test_cached_served_when_offline(self, online_chain: OfflineFallbackChain) -> None:
        # Prime the cache
        online_chain.call("test_tool", "x")
        online_chain.set_state(OnlineState.OFFLINE)
        result = online_chain.call("test_tool", "x")
        assert result.outcome == FallbackOutcome.CACHED
        assert result.value == "primary_response"

    def test_cache_age_reported(self, online_chain: OfflineFallbackChain) -> None:
        online_chain.call("test_tool", "y")
        online_chain.set_state(OnlineState.OFFLINE)
        result = online_chain.call("test_tool", "y")
        assert result.cache_age_seconds is not None
        assert result.cache_age_seconds >= 0.0

    def test_different_args_different_cache_entry(
        self, online_chain: OfflineFallbackChain
    ) -> None:
        online_chain.call("test_tool", "a")
        online_chain.set_state(OnlineState.OFFLINE)
        # "b" was never cached — should fall through to local
        result = online_chain.call("test_tool", "b")
        assert result.outcome == FallbackOutcome.LOCAL

    def test_cache_disabled_skips_tier(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "no_cache_tool", enable_cache=False, enable_local=True, enable_queue=False
        )
        chain.register_tool(strategy, primary=_failing_primary, local_alt=_local_alt)
        result = chain.call("no_cache_tool")
        assert result.outcome == FallbackOutcome.LOCAL


# ---------------------------------------------------------------------------
# Local tier tests
# ---------------------------------------------------------------------------


class TestLocalTier:
    def test_local_fallback_when_offline_no_cache(
        self, offline_chain: OfflineFallbackChain
    ) -> None:
        result = offline_chain.call("test_tool", "uncached_arg")
        assert result.outcome == FallbackOutcome.LOCAL
        assert result.value == "local_response"

    def test_local_disabled_skips_tier(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "no_local_tool", enable_cache=False, enable_local=False, enable_queue=True
        )
        chain.register_tool(strategy, primary=_failing_primary)
        result = chain.call("no_local_tool")
        assert result.outcome == FallbackOutcome.QUEUED

    def test_local_without_alt_registered_skips(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "no_alt_tool", enable_cache=False, enable_local=True, enable_queue=True
        )
        # No local_alt registered
        chain.register_tool(strategy, primary=_failing_primary)
        result = chain.call("no_alt_tool")
        assert result.outcome == FallbackOutcome.QUEUED


# ---------------------------------------------------------------------------
# Queue tier tests
# ---------------------------------------------------------------------------


class TestQueueTier:
    def test_queued_when_all_tiers_fail(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "queue_only_tool",
            enable_cache=False,
            enable_local=False,
            enable_queue=True,
        )
        chain.register_tool(strategy, primary=_failing_primary)
        result = chain.call("queue_only_tool", "arg")
        assert result.outcome == FallbackOutcome.QUEUED
        assert result.value is None

    def test_queue_size_increments(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "q_tool", enable_cache=False, enable_local=False, enable_queue=True
        )
        chain.register_tool(strategy, primary=_failing_primary)
        chain.call("q_tool", 1)
        chain.call("q_tool", 2)
        assert chain.get_queue_size("q_tool") == 2

    def test_flush_queue_retries_calls(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "flush_tool", enable_cache=False, enable_local=False, enable_queue=True
        )
        chain.register_tool(strategy, primary=_make_primary("flushed"))
        chain.call("flush_tool", "deferred_arg")
        chain.set_state(OnlineState.ONLINE)
        results = chain.flush_queue("flush_tool")
        assert len(results) == 1
        assert results[0].outcome == FallbackOutcome.PRIMARY
        assert chain.get_queue_size("flush_tool") == 0

    def test_queue_disabled_returns_failed(self) -> None:
        chain = OfflineFallbackChain(initial_state=OnlineState.OFFLINE)
        strategy = FallbackStrategy(
            "no_queue_tool",
            enable_cache=False,
            enable_local=False,
            enable_queue=False,
        )
        chain.register_tool(strategy, primary=_failing_primary)
        result = chain.call("no_queue_tool")
        assert result.outcome == FallbackOutcome.FAILED
        assert result.error is not None


# ---------------------------------------------------------------------------
# Statistics and metadata tests
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_call_stats_tracked(self, online_chain: OfflineFallbackChain) -> None:
        online_chain.call("test_tool")
        stats = online_chain.get_call_stats("test_tool")
        assert stats["primary"] == 1

    def test_call_stats_multiple_tiers(self, online_chain: OfflineFallbackChain) -> None:
        online_chain.call("test_tool", "cached_arg")
        online_chain.set_state(OnlineState.OFFLINE)
        online_chain.call("test_tool", "cached_arg")  # cached
        online_chain.call("test_tool", "new_arg")  # local
        stats = online_chain.get_call_stats("test_tool")
        assert stats["primary"] >= 1
        assert stats["cached"] >= 1

    def test_result_has_served_at(self, online_chain: OfflineFallbackChain) -> None:
        result = online_chain.call("test_tool")
        assert result.served_at is not None

    def test_flush_queue_empty_returns_empty_list(
        self, online_chain: OfflineFallbackChain
    ) -> None:
        results = online_chain.flush_queue("test_tool")
        assert results == []

    def test_get_queue_size_unknown_tool_returns_zero(
        self, online_chain: OfflineFallbackChain
    ) -> None:
        assert online_chain.get_queue_size("unknown") == 0
