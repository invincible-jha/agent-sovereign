"""Shared bootstrap for agent-sovereign benchmarks."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_SRC = _REPO_ROOT / "src"
_BENCHMARKS = _REPO_ROOT / "benchmarks"

for _path in [str(_SRC), str(_BENCHMARKS)]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.compliance.checker import SovereigntyComplianceChecker
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator

__all__ = [
    "SovereigntyLevel",
    "SovereigntyComplianceChecker",
    "DeploymentConfig",
    "DeploymentValidator",
]
