"""Residency sub-package for agent-sovereign.

Provides data residency policy enforcement, jurisdiction mapping,
and compliant region lookup for sovereign deployments.
"""
from __future__ import annotations

from agent_sovereign.residency.mapper import JurisdictionMapper, JurisdictionRequirements
from agent_sovereign.residency.policy import DataResidencyPolicy, ResidencyChecker

__all__ = [
    "DataResidencyPolicy",
    "JurisdictionMapper",
    "JurisdictionRequirements",
    "ResidencyChecker",
]
