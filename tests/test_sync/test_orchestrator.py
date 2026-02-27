"""Tests for agent_sovereign.sync.orchestrator."""
from __future__ import annotations

import datetime

import pytest

from agent_sovereign.sync.orchestrator import (
    ConflictResolution,
    SyncItem,
    SyncOrchestrator,
    SyncPriority,
    SyncStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    item_id: str = "i1",
    key: str = "key/a",
    value: object = "local_data",
    priority: SyncPriority = SyncPriority.NORMAL,
    remote_value: object | None = None,
    remote_ts: datetime.datetime | None = None,
    conflict: ConflictResolution = ConflictResolution.LAST_WRITE_WINS,
) -> SyncItem:
    return SyncItem(
        item_id=item_id,
        key=key,
        local_value=value,
        priority=priority,
        remote_value=remote_value,
        remote_modified_at=remote_ts,
        conflict_resolution=conflict,
    )


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _past(seconds: int = 60) -> datetime.datetime:
    return _now() - datetime.timedelta(seconds=seconds)


def _future(seconds: int = 60) -> datetime.datetime:
    return _now() + datetime.timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def orchestrator() -> SyncOrchestrator:
    return SyncOrchestrator()


# ---------------------------------------------------------------------------
# Enqueue and queue management
# ---------------------------------------------------------------------------


class TestQueueManagement:
    def test_enqueue_single_item(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        assert orchestrator.queue_size() == 1

    def test_enqueue_batch(self, orchestrator: SyncOrchestrator) -> None:
        items = [_make_item(str(i)) for i in range(5)]
        orchestrator.enqueue_batch(items)
        assert orchestrator.queue_size() == 5

    def test_get_pending_sorted_by_priority(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("low", priority=SyncPriority.LOW))
        orchestrator.enqueue(_make_item("critical", priority=SyncPriority.CRITICAL))
        orchestrator.enqueue(_make_item("normal", priority=SyncPriority.NORMAL))
        pending = orchestrator.get_pending()
        assert pending[0].item_id == "critical"
        assert pending[-1].item_id == "low"

    def test_queue_size_excludes_synced(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        orchestrator.sync_all()
        assert orchestrator.queue_size() == 0


# ---------------------------------------------------------------------------
# Basic sync
# ---------------------------------------------------------------------------


class TestBasicSync:
    def test_sync_all_returns_results(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        results = orchestrator.sync_all()
        assert len(results) == 1

    def test_sync_result_status_synced(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        results = orchestrator.sync_all()
        assert results[0].status == SyncStatus.SYNCED

    def test_sync_result_has_value(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1", value="my_data"))
        results = orchestrator.sync_all()
        assert results[0].conflict_resolved_value == "my_data"

    def test_sync_priority_filters_by_level(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("crit", priority=SyncPriority.CRITICAL))
        orchestrator.enqueue(_make_item("norm", priority=SyncPriority.NORMAL))
        results = orchestrator.sync_priority(SyncPriority.CRITICAL)
        assert len(results) == 1
        assert results[0].item_id == "crit"

    def test_empty_queue_returns_empty_list(self, orchestrator: SyncOrchestrator) -> None:
        results = orchestrator.sync_all()
        assert results == []


# ---------------------------------------------------------------------------
# Delta sync
# ---------------------------------------------------------------------------


class TestDeltaSync:
    def test_unchanged_item_is_skipped_on_second_sync(
        self, orchestrator: SyncOrchestrator
    ) -> None:
        item = _make_item("i1", key="key/delta", value="same_data")
        orchestrator.enqueue(item)
        orchestrator.sync_all()

        # Re-enqueue with same value
        item2 = _make_item("i2", key="key/delta", value="same_data")
        orchestrator.enqueue(item2)
        results = orchestrator.sync_all()
        assert results[0].status == SyncStatus.SKIPPED

    def test_changed_item_is_synced(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1", key="key/delta", value="v1"))
        orchestrator.sync_all()

        orchestrator.enqueue(_make_item("i2", key="key/delta", value="v2"))
        results = orchestrator.sync_all()
        assert results[0].status == SyncStatus.SYNCED


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    def test_last_write_wins_local_newer(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c1",
            key="key/conflict",
            local_value="local_v",
            local_modified_at=_future(10),
            remote_value="remote_v",
            remote_modified_at=_past(10),
            conflict_resolution=ConflictResolution.LAST_WRITE_WINS,
        )
        orchestrator.enqueue(item)
        results = orchestrator.sync_all()
        assert results[0].conflict_resolved_value == "local_v"

    def test_last_write_wins_remote_newer(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c2",
            key="key/conflict2",
            local_value="local_v",
            local_modified_at=_past(10),
            remote_value="remote_v",
            remote_modified_at=_future(10),
            conflict_resolution=ConflictResolution.LAST_WRITE_WINS,
        )
        orchestrator.enqueue(item)
        results = orchestrator.sync_all()
        assert results[0].conflict_resolved_value == "remote_v"

    def test_local_wins_strategy(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c3",
            key="key/local_wins",
            local_value="local_v",
            local_modified_at=_past(10),
            remote_value="remote_v",
            remote_modified_at=_future(10),
            conflict_resolution=ConflictResolution.LOCAL_WINS,
        )
        orchestrator.enqueue(item)
        results = orchestrator.sync_all()
        assert results[0].conflict_resolved_value == "local_v"

    def test_remote_wins_strategy(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c4",
            key="key/remote_wins",
            local_value="local_v",
            local_modified_at=_future(10),
            remote_value="remote_v",
            remote_modified_at=_past(10),
            conflict_resolution=ConflictResolution.REMOTE_WINS,
        )
        orchestrator.enqueue(item)
        results = orchestrator.sync_all()
        assert results[0].conflict_resolved_value == "remote_v"

    def test_manual_conflict_flags_item(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c5",
            key="key/manual",
            local_value="local_v",
            local_modified_at=_now(),
            remote_value="remote_v",
            remote_modified_at=_now(),
            conflict_resolution=ConflictResolution.MANUAL,
        )
        orchestrator.enqueue(item)
        results = orchestrator.sync_all()
        assert results[0].status == SyncStatus.CONFLICT
        assert len(orchestrator.get_manual_conflicts()) == 1

    def test_resolve_manual_conflict(self, orchestrator: SyncOrchestrator) -> None:
        item = SyncItem(
            item_id="c6",
            key="key/manual_res",
            local_value="local_v",
            local_modified_at=_now(),
            remote_value="remote_v",
            remote_modified_at=_now(),
            conflict_resolution=ConflictResolution.MANUAL,
        )
        orchestrator.enqueue(item)
        orchestrator.sync_all()
        result = orchestrator.resolve_manual_conflict("c6", "chosen_v")
        assert result.status == SyncStatus.SYNCED
        assert result.conflict_resolved_value == "chosen_v"
        assert len(orchestrator.get_manual_conflicts()) == 0

    def test_resolve_unknown_conflict_raises(self, orchestrator: SyncOrchestrator) -> None:
        with pytest.raises(KeyError):
            orchestrator.resolve_manual_conflict("nonexistent", "val")


# ---------------------------------------------------------------------------
# History and statistics
# ---------------------------------------------------------------------------


class TestHistoryAndStats:
    def test_history_grows_with_syncs(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        orchestrator.enqueue(_make_item("i2"))
        orchestrator.sync_all()
        assert len(orchestrator.get_history()) == 2

    def test_stats_counts_synced(self, orchestrator: SyncOrchestrator) -> None:
        orchestrator.enqueue(_make_item("i1"))
        orchestrator.sync_all()
        stats = orchestrator.get_stats()
        assert stats["synced"] == 1

    def test_stats_has_all_status_keys(self, orchestrator: SyncOrchestrator) -> None:
        stats = orchestrator.get_stats()
        for status in SyncStatus:
            assert status.value in stats

    def test_priority_enum_ordering(self) -> None:
        assert SyncPriority.CRITICAL.value < SyncPriority.HIGH.value
        assert SyncPriority.HIGH.value < SyncPriority.NORMAL.value
        assert SyncPriority.NORMAL.value < SyncPriority.LOW.value
