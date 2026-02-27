"""Sync orchestrator for edge-to-cloud data synchronisation.

Implements a priority-based sync queue with delta-sync (only changed data)
and pluggable conflict resolution strategies.

Priorities
----------
CRITICAL : Must sync immediately — e.g. safety events, audit logs.
HIGH     : Sync on next cycle — e.g. session state, user preferences.
NORMAL   : Best-effort sync — e.g. telemetry, analytics.
LOW      : Batch when convenient — e.g. debug traces, model logs.

Conflict Resolution
-------------------
LAST_WRITE_WINS : The most recent timestamp wins (default).
MANUAL          : Conflict is flagged; a human resolver must decide.
LOCAL_WINS      : Edge-side data always takes precedence.
REMOTE_WINS     : Cloud-side data always takes precedence.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SyncPriority(int, Enum):
    """Sync priority tier — lower numeric value = higher priority."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class SyncStatus(str, Enum):
    """Status of a sync item."""

    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SYNCED = "synced"
    CONFLICT = "conflict"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConflictResolution(str, Enum):
    """Strategy for resolving sync conflicts."""

    LAST_WRITE_WINS = "last_write_wins"
    MANUAL = "manual"
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"


# ---------------------------------------------------------------------------
# Sync item
# ---------------------------------------------------------------------------


@dataclass
class SyncItem:
    """A single item to be synchronised.

    Attributes
    ----------
    item_id:
        Unique identifier for this item.
    key:
        Logical data key (e.g. "session/abc/state").
    local_value:
        The local (edge-side) value to sync.
    remote_value:
        The last known remote (cloud-side) value, or None if unknown.
    local_modified_at:
        UTC timestamp of the most recent local modification.
    remote_modified_at:
        UTC timestamp of the most recent remote modification, or None.
    priority:
        The :class:`SyncPriority` for this item.
    status:
        Current :class:`SyncStatus`.
    conflict_resolution:
        Conflict resolution strategy to apply.
    local_checksum:
        SHA-256 of ``local_value`` for delta-sync comparison.
    synced_at:
        UTC timestamp of when this item was last successfully synced.
    error:
        Error message if status is FAILED.
    """

    item_id: str
    key: str
    local_value: object
    priority: SyncPriority = SyncPriority.NORMAL
    remote_value: object = None
    local_modified_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    remote_modified_at: datetime.datetime | None = None
    status: SyncStatus = SyncStatus.PENDING
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS
    local_checksum: str = ""
    synced_at: datetime.datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Compute checksum on creation if not provided."""
        if not self.local_checksum:
            self.local_checksum = self._compute_checksum(self.local_value)

    @staticmethod
    def _compute_checksum(value: object) -> str:
        """Compute a stable SHA-256 of a value's string representation."""
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    def has_changed(self, previous_checksum: str) -> bool:
        """Return True if local value has changed vs *previous_checksum*."""
        return self.local_checksum != previous_checksum


# ---------------------------------------------------------------------------
# Sync result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a single sync attempt.

    Attributes
    ----------
    item_id:
        ID of the synced item.
    key:
        Logical key.
    status:
        Resulting :class:`SyncStatus`.
    conflict_resolved_value:
        The winning value after conflict resolution, or None.
    synced_at:
        UTC timestamp of the sync attempt.
    error:
        Error message if failed.
    """

    item_id: str
    key: str
    status: SyncStatus
    conflict_resolved_value: object = None
    synced_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    error: str | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class SyncOrchestrator:
    """Priority-based sync orchestrator with delta-sync and conflict resolution.

    Items are queued with a priority and synced in order: CRITICAL first,
    then HIGH, NORMAL, LOW.  Delta-sync skips items whose checksum has not
    changed since the last successful sync.

    Parameters
    ----------
    default_conflict_resolution:
        Default strategy used when an item does not specify one.

    Example
    -------
    ::

        orchestrator = SyncOrchestrator()
        orchestrator.enqueue(SyncItem("s1", "key/a", {"data": 1}))
        results = orchestrator.sync_all()
    """

    def __init__(
        self,
        default_conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS,
    ) -> None:
        self._default_conflict = default_conflict_resolution
        self._queue: list[SyncItem] = []
        self._checksums: dict[str, str] = {}  # key → last synced checksum
        self._history: list[SyncResult] = []
        self._manual_conflicts: list[SyncItem] = []

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def enqueue(self, item: SyncItem) -> None:
        """Add an item to the sync queue.

        Parameters
        ----------
        item:
            The :class:`SyncItem` to queue for synchronisation.
        """
        if not item.conflict_resolution:
            item.conflict_resolution = self._default_conflict
        self._queue.append(item)
        logger.debug("Enqueued sync item %s (priority=%s)", item.item_id, item.priority.name)

    def enqueue_batch(self, items: list[SyncItem]) -> None:
        """Add multiple items to the sync queue.

        Parameters
        ----------
        items:
            List of :class:`SyncItem` objects to enqueue.
        """
        for item in items:
            self.enqueue(item)

    def queue_size(self) -> int:
        """Return the number of items currently pending sync."""
        return sum(1 for i in self._queue if i.status == SyncStatus.PENDING)

    def get_pending(self) -> list[SyncItem]:
        """Return pending items ordered by priority (CRITICAL first).

        Returns
        -------
        list[SyncItem]
            Items with status PENDING, sorted by priority value.
        """
        pending = [i for i in self._queue if i.status == SyncStatus.PENDING]
        return sorted(pending, key=lambda i: i.priority.value)

    # ------------------------------------------------------------------
    # Sync execution
    # ------------------------------------------------------------------

    def sync_all(self) -> list[SyncResult]:
        """Process all pending items in priority order.

        Applies delta-sync: items whose checksum matches the last synced
        checksum are skipped.  Conflicts are resolved according to each
        item's strategy.

        Returns
        -------
        list[SyncResult]
            One result per processed item.
        """
        results: list[SyncResult] = []
        for item in self.get_pending():
            result = self._sync_item(item)
            results.append(result)
            self._history.append(result)
        return results

    def sync_priority(self, priority: SyncPriority) -> list[SyncResult]:
        """Sync only items at the given priority level.

        Parameters
        ----------
        priority:
            The :class:`SyncPriority` tier to process.

        Returns
        -------
        list[SyncResult]
            Results for the processed items.
        """
        results: list[SyncResult] = []
        items = [i for i in self._queue if i.status == SyncStatus.PENDING and i.priority == priority]
        for item in items:
            result = self._sync_item(item)
            results.append(result)
            self._history.append(result)
        return results

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def resolve_manual_conflict(self, item_id: str, chosen_value: object) -> SyncResult:
        """Resolve a manually-flagged conflict by supplying the winning value.

        Parameters
        ----------
        item_id:
            The ID of the item in MANUAL conflict.
        chosen_value:
            The value that should be used as the resolved value.

        Returns
        -------
        SyncResult
            Result with status SYNCED and the resolved value.

        Raises
        ------
        KeyError
            If *item_id* is not in the manual conflict list.
        """
        conflicted = next((i for i in self._manual_conflicts if i.item_id == item_id), None)
        if conflicted is None:
            raise KeyError(f"No manual conflict found for item_id={item_id!r}")

        self._manual_conflicts.remove(conflicted)
        self._checksums[conflicted.key] = SyncItem._compute_checksum(chosen_value)
        conflicted.status = SyncStatus.SYNCED
        now = datetime.datetime.now(datetime.timezone.utc)
        result = SyncResult(
            item_id=item_id,
            key=conflicted.key,
            status=SyncStatus.SYNCED,
            conflict_resolved_value=chosen_value,
            synced_at=now,
        )
        self._history.append(result)
        return result

    def get_manual_conflicts(self) -> list[SyncItem]:
        """Return items awaiting manual conflict resolution."""
        return list(self._manual_conflicts)

    # ------------------------------------------------------------------
    # History / statistics
    # ------------------------------------------------------------------

    def get_history(self) -> list[SyncResult]:
        """Return all sync results produced so far."""
        return list(self._history)

    def get_stats(self) -> dict[str, int]:
        """Return counts per :class:`SyncStatus` across all history.

        Returns
        -------
        dict[str, int]
            Mapping of status name to count.
        """
        counts: dict[str, int] = {status.value: 0 for status in SyncStatus}
        for result in self._history:
            counts[result.status.value] += 1
        return counts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sync_item(self, item: SyncItem) -> SyncResult:
        """Process a single :class:`SyncItem` through the sync pipeline."""
        item.status = SyncStatus.IN_FLIGHT
        now = datetime.datetime.now(datetime.timezone.utc)

        # Delta sync — skip if checksum unchanged
        last_checksum = self._checksums.get(item.key, "")
        if last_checksum and not item.has_changed(last_checksum):
            item.status = SyncStatus.SKIPPED
            logger.debug("Delta-sync: skipping %s (unchanged)", item.item_id)
            return SyncResult(
                item_id=item.item_id,
                key=item.key,
                status=SyncStatus.SKIPPED,
                synced_at=now,
            )

        # Conflict detection
        if item.remote_value is not None and item.remote_modified_at is not None:
            conflict_result = self._handle_conflict(item, now)
            if conflict_result is not None:
                return conflict_result

        # No conflict — accept local value
        self._checksums[item.key] = item.local_checksum
        item.status = SyncStatus.SYNCED
        item.synced_at = now
        logger.debug("Synced item %s", item.item_id)
        return SyncResult(
            item_id=item.item_id,
            key=item.key,
            status=SyncStatus.SYNCED,
            conflict_resolved_value=item.local_value,
            synced_at=now,
        )

    def _handle_conflict(self, item: SyncItem, now: datetime.datetime) -> SyncResult | None:
        """Apply conflict resolution strategy.

        Returns a :class:`SyncResult` if a conflict was detected and
        handled, or None if no conflict exists.
        """
        local_ts = item.local_modified_at
        remote_ts = item.remote_modified_at

        if local_ts == remote_ts:
            # Timestamps equal — check if values differ
            remote_checksum = SyncItem._compute_checksum(item.remote_value)
            if item.local_checksum == remote_checksum:
                # No actual conflict — values are the same
                return None

        strategy = item.conflict_resolution or self._default_conflict

        if strategy == ConflictResolution.LAST_WRITE_WINS:
            if remote_ts is not None and remote_ts > local_ts:
                winning_value = item.remote_value
            else:
                winning_value = item.local_value
            self._checksums[item.key] = SyncItem._compute_checksum(winning_value)
            item.status = SyncStatus.SYNCED
            item.synced_at = now
            return SyncResult(
                item_id=item.item_id,
                key=item.key,
                status=SyncStatus.SYNCED,
                conflict_resolved_value=winning_value,
                synced_at=now,
            )

        if strategy == ConflictResolution.LOCAL_WINS:
            winning_value = item.local_value
            self._checksums[item.key] = item.local_checksum
            item.status = SyncStatus.SYNCED
            item.synced_at = now
            return SyncResult(
                item_id=item.item_id,
                key=item.key,
                status=SyncStatus.SYNCED,
                conflict_resolved_value=winning_value,
                synced_at=now,
            )

        if strategy == ConflictResolution.REMOTE_WINS:
            winning_value = item.remote_value
            self._checksums[item.key] = SyncItem._compute_checksum(winning_value)
            item.status = SyncStatus.SYNCED
            item.synced_at = now
            return SyncResult(
                item_id=item.item_id,
                key=item.key,
                status=SyncStatus.SYNCED,
                conflict_resolved_value=winning_value,
                synced_at=now,
            )

        if strategy == ConflictResolution.MANUAL:
            item.status = SyncStatus.CONFLICT
            self._manual_conflicts.append(item)
            logger.warning("Manual conflict flagged for item %s", item.item_id)
            return SyncResult(
                item_id=item.item_id,
                key=item.key,
                status=SyncStatus.CONFLICT,
                synced_at=now,
            )

        return None


__all__ = [
    "ConflictResolution",
    "SyncItem",
    "SyncOrchestrator",
    "SyncPriority",
    "SyncResult",
    "SyncStatus",
]
