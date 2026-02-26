"""Edge sub-package for agent-sovereign.

Provides edge runtime configuration, offline mode management, and
synchronisation policies for edge-deployed agent bundles.
"""
from __future__ import annotations

from agent_sovereign.edge.offline import OfflineCapability, OfflineManager
from agent_sovereign.edge.runtime import EdgeConfig, EdgeRuntime
from agent_sovereign.edge.sync import SyncManager, SyncPolicy

__all__ = [
    "EdgeConfig",
    "EdgeRuntime",
    "OfflineCapability",
    "OfflineManager",
    "SyncManager",
    "SyncPolicy",
]
