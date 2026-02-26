"""Provenance sub-package for agent-sovereign.

Provides model provenance tracking, chain-of-custody verification,
and HMAC-based attestation for deployed model artefacts.
"""
from __future__ import annotations

from agent_sovereign.provenance.attestation import Attestation, AttestationGenerator
from agent_sovereign.provenance.tracker import ModelProvenance, ProvenanceTracker

__all__ = [
    "Attestation",
    "AttestationGenerator",
    "ModelProvenance",
    "ProvenanceTracker",
]
