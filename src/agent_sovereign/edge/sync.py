"""Edge synchronisation manager.

Manages a queue of pending synchronisation tasks between edge nodes and
central infrastructure, respecting the sovereignty and connectivity policies
of the deployment.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum


class SyncPriority(str, Enum):
    """Priority level for a sync task."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SyncTaskStatus(str, Enum):
    """Lifecycle state of a sync task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SyncPolicy:
    """Policy governing when and how synchronisation may occur.

    Attributes
    ----------
    allow_background_sync:
        Whether sync tasks may run in the background without user interaction.
    max_retry_attempts:
        Maximum number of retry attempts for a failed sync task.
    retry_backoff_seconds:
        Base backoff interval in seconds between retry attempts.
    sync_window_start_hour:
        UTC hour (0–23) at which the sync window opens (inclusive).
        Set to -1 to allow sync at any time.
    sync_window_end_hour:
        UTC hour (0–23) at which the sync window closes (inclusive).
        Set to -1 to allow sync at any time.
    require_encrypted_channel:
        Whether sync must only proceed over an encrypted channel.
    max_payload_size_mb:
        Maximum size of a single sync payload in MiB.
    allowed_sync_types:
        If non-empty, only sync tasks with a type in this set are allowed.
    """

    allow_background_sync: bool = True
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 30.0
    sync_window_start_hour: int = -1
    sync_window_end_hour: int = -1
    require_encrypted_channel: bool = True
    max_payload_size_mb: float = 100.0
    allowed_sync_types: list[str] = field(default_factory=list)


@dataclass
class SyncTask:
    """A single unit of work to synchronise.

    Attributes
    ----------
    task_id:
        Unique identifier for this sync task.
    sync_type:
        Category of sync (e.g. "model_update", "audit_log", "telemetry").
    payload_description:
        Human-readable description of what this task syncs.
    priority:
        Task priority affecting processing order.
    status:
        Current lifecycle state.
    created_at:
        ISO-8601 UTC timestamp of task creation.
    updated_at:
        ISO-8601 UTC timestamp of last status change.
    retry_count:
        Number of retry attempts made so far.
    error_message:
        Last error message if the task failed.
    metadata:
        Arbitrary key/value metadata attached to this task.
    """

    task_id: str
    sync_type: str
    payload_description: str
    priority: SyncPriority = SyncPriority.NORMAL
    status: SyncTaskStatus = SyncTaskStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    retry_count: int = 0
    error_message: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class SyncManager:
    """Manages the sync task queue for an edge node.

    Enqueues sync tasks, processes the queue according to the active
    SyncPolicy, and tracks status for all tasks.

    Parameters
    ----------
    policy:
        The SyncPolicy governing sync behaviour. Can be updated at runtime
        via ``update_policy``.
    """

    def __init__(self, policy: SyncPolicy | None = None) -> None:
        self._policy = policy or SyncPolicy()
        self._queue: list[SyncTask] = []
        self._completed: list[SyncTask] = []

    def update_policy(self, policy: SyncPolicy) -> None:
        """Replace the active sync policy.

        Parameters
        ----------
        policy:
            New SyncPolicy to apply to subsequent queue operations.
        """
        self._policy = policy

    def queue_sync(
        self,
        sync_type: str,
        payload_description: str,
        priority: SyncPriority = SyncPriority.NORMAL,
        metadata: dict[str, str] | None = None,
    ) -> SyncTask:
        """Add a sync task to the pending queue.

        Parameters
        ----------
        sync_type:
            Category of the sync task (e.g. "model_update").
        payload_description:
            Human-readable description of what will be synced.
        priority:
            Task priority. Higher-priority tasks are processed first.
        metadata:
            Optional metadata key/value pairs for the task.

        Returns
        -------
        SyncTask
            The newly created and enqueued task.

        Raises
        ------
        ValueError
            If ``sync_type`` is not in ``policy.allowed_sync_types`` when
            that list is non-empty.
        """
        allowed = self._policy.allowed_sync_types
        if allowed and sync_type not in allowed:
            raise ValueError(
                f"Sync type {sync_type!r} is not permitted by the current SyncPolicy. "
                f"Allowed types: {allowed}"
            )

        task = SyncTask(
            task_id=str(uuid.uuid4()),
            sync_type=sync_type,
            payload_description=payload_description,
            priority=priority,
            metadata=metadata or {},
        )
        self._queue.append(task)
        return task

    def process_queue(
        self,
        processor: SyncTaskProcessor | None = None,
    ) -> list[SyncTask]:
        """Process all pending tasks in priority order.

        Tasks are sorted by priority (CRITICAL first) before processing.
        Each task is passed to the ``processor`` callable if provided;
        otherwise a no-op simulation marks tasks as COMPLETED.

        Only processes tasks that are within the sync window defined by
        the active SyncPolicy (if a window is configured).

        Parameters
        ----------
        processor:
            Optional callable that takes a SyncTask and returns True if
            the task succeeded, False if it failed. If None, all tasks
            are simulated as successful.

        Returns
        -------
        list[SyncTask]
            The list of tasks that were processed in this call (not all
            tasks in the store).
        """
        if not self._is_within_sync_window():
            return []

        priority_order = {
            SyncPriority.CRITICAL: 0,
            SyncPriority.HIGH: 1,
            SyncPriority.NORMAL: 2,
            SyncPriority.LOW: 3,
        }
        pending = [t for t in self._queue if t.status == SyncTaskStatus.PENDING]
        pending.sort(key=lambda t: priority_order.get(t.priority, 99))

        processed: list[SyncTask] = []
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for task in pending:
            task.status = SyncTaskStatus.IN_PROGRESS
            task.updated_at = now_iso

            success = processor(task) if processor is not None else True

            if success:
                task.status = SyncTaskStatus.COMPLETED
            else:
                task.retry_count += 1
                if task.retry_count >= self._policy.max_retry_attempts:
                    task.status = SyncTaskStatus.FAILED
                else:
                    task.status = SyncTaskStatus.PENDING  # will retry

            task.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            processed.append(task)

        # Move completed and failed tasks to history
        for task in list(self._queue):
            if task.status in (SyncTaskStatus.COMPLETED, SyncTaskStatus.FAILED):
                self._completed.append(task)
                self._queue.remove(task)

        return processed

    def get_pending_count(self) -> int:
        """Return the number of tasks currently pending in the queue.

        Returns
        -------
        int
            Count of tasks with status PENDING.
        """
        return sum(1 for t in self._queue if t.status == SyncTaskStatus.PENDING)

    def get_all_tasks(self) -> list[SyncTask]:
        """Return all tasks: both queued and completed.

        Returns
        -------
        list[SyncTask]
            Combined list of active queue and completed history.
        """
        return list(self._queue) + list(self._completed)

    def clear_completed(self) -> int:
        """Remove all completed tasks from history.

        Returns
        -------
        int
            Number of tasks removed.
        """
        count = len(self._completed)
        self._completed.clear()
        return count

    def _is_within_sync_window(self) -> bool:
        """Return True if the current UTC time is within the configured sync window."""
        start = self._policy.sync_window_start_hour
        end = self._policy.sync_window_end_hour
        if start == -1 or end == -1:
            return True
        current_hour = datetime.datetime.now(datetime.timezone.utc).hour
        if start <= end:
            return start <= current_hour <= end
        # Window wraps midnight
        return current_hour >= start or current_hour <= end


class SyncTaskProcessor:
    """Protocol-like base for sync task processors.

    Subclass this and implement ``__call__`` to integrate with real
    sync endpoints or message queues. The SyncManager will call
    ``processor(task)`` for each pending task.
    """

    def __call__(self, task: SyncTask) -> bool:
        """Process a sync task.

        Parameters
        ----------
        task:
            The task to process.

        Returns
        -------
        bool
            True if the task completed successfully, False otherwise.
        """
        raise NotImplementedError


__all__ = [
    "SyncManager",
    "SyncPolicy",
    "SyncPriority",
    "SyncTask",
    "SyncTaskProcessor",
    "SyncTaskStatus",
]
