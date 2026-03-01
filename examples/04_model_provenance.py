#!/usr/bin/env python3
"""Example: Model Provenance and Attestation

Demonstrates recording model provenance, generating attestations,
and verifying the integrity of deployed models.

Usage:
    python examples/04_model_provenance.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    Attestation,
    AttestationGenerator,
    ModelProvenance,
    ProvenanceTracker,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Record model provenance
    tracker = ProvenanceTracker()
    models: list[ModelProvenance] = [
        ModelProvenance(
            model_id="local-llm-7b-v1",
            source="internal-registry",
            version="1.0.0",
            training_data_hash="sha256:abc123",
            license="Apache-2.0",
            provider="MuVeraAI",
        ),
        ModelProvenance(
            model_id="local-embedder-v1",
            source="internal-registry",
            version="1.1.0",
            training_data_hash="sha256:def456",
            license="MIT",
            provider="MuVeraAI",
        ),
        ModelProvenance(
            model_id="safety-classifier-v2",
            source="internal-registry",
            version="2.0.0",
            training_data_hash="sha256:ghi789",
            license="Apache-2.0",
            provider="MuVeraAI",
        ),
    ]

    for model in models:
        tracker.record(model)
    print(f"Recorded {tracker.count()} model provenance entries")

    # Step 2: Retrieve provenance
    retrieved = tracker.get("local-llm-7b-v1")
    print(f"\nProvenance for '{retrieved.model_id}':")
    print(f"  Source: {retrieved.source}")
    print(f"  Version: {retrieved.version}")
    print(f"  License: {retrieved.license}")
    print(f"  Training hash: {retrieved.training_data_hash[:30]}")

    # Step 3: Generate attestations
    generator = AttestationGenerator()
    attestations: list[Attestation] = []
    for model in models:
        att = generator.generate(
            model_id=model.model_id,
            deployment_id="deploy-eu-001",
            signer="MuVeraAI-ops",
        )
        attestations.append(att)
        print(f"\nAttestation for '{model.model_id}':")
        print(f"  Attestation ID: {att.attestation_id}")
        print(f"  Signed by: {att.signer}")
        print(f"  Signature: {att.signature[:30]}...")

    # Step 4: Verify attestations
    print(f"\nVerification results:")
    for att in attestations:
        valid = generator.verify(att)
        print(f"  [{att.model_id}]: {'VALID' if valid else 'INVALID'}")

    # Step 5: List all tracked models
    all_models = tracker.list()
    print(f"\nAll tracked models ({len(all_models)}):")
    for model in all_models:
        print(f"  {model.model_id} v{model.version} ({model.license})")


if __name__ == "__main__":
    main()
