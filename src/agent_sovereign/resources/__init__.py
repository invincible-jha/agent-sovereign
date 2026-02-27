"""Resource detection and profile subpackage."""
from __future__ import annotations

from agent_sovereign.resources.resource_detector import (
    BatchSizeRecommendation,
    ModelSizeRecommendation,
    ResourceDetector,
    ResourceProfile,
)

__all__ = [
    "BatchSizeRecommendation",
    "ModelSizeRecommendation",
    "ResourceDetector",
    "ResourceProfile",
]
