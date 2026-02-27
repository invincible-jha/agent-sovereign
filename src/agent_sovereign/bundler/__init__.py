"""Sovereign one-command deployment bundler for agent-sovereign.

Phase 7A of the AumOS implementation plan.  Provides a complete pipeline
for packaging, containerising, and attesting self-contained agent bundles
so they can be deployed with a single command at any sovereignty level.

Submodules
----------
- ``manifest``         BundleManifest, BundleComponent, SovereigntyLevel enum
- ``docker_generator`` DockerGenerator for Dockerfile / Compose generation
- ``packager``         AgentPackager — scans sources, computes checksums
- ``attestation``      AttestationGenerator — build provenance and integrity
"""
from __future__ import annotations

from agent_sovereign.bundler.attestation import (
    Attestation,
    AttestationGenerator,
    AttestationType,
)
from agent_sovereign.bundler.docker_generator import DockerConfig, DockerGenerator
from agent_sovereign.bundler.manifest import (
    BundleComponent,
    BundleManifest,
    BundleSovereigntyLevel,
)
from agent_sovereign.bundler.packager import AgentPackager, PackageConfig

__all__ = [
    # Manifest
    "BundleComponent",
    "BundleManifest",
    "BundleSovereigntyLevel",
    # Docker
    "DockerConfig",
    "DockerGenerator",
    # Packager
    "AgentPackager",
    "PackageConfig",
    # Attestation
    "Attestation",
    "AttestationGenerator",
    "AttestationType",
]
