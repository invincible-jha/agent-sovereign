#!/usr/bin/env python3
"""Example: Deployment Packaging and Validation

Demonstrates generating deployment packages with manifests and
validating configuration against sovereignty requirements.

Usage:
    python examples/03_deployment_packaging.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    DeploymentConfig,
    DeploymentPackager,
    DeploymentValidator,
    SovereigntyLevel,
    TemplateLibrary,
    ValidationStatus,
    get_template,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Inspect template library
    library = TemplateLibrary()
    available_levels = library.list_levels()
    print(f"Available deployment templates: {[f'L{l.value}' for l in available_levels]}")

    # Step 2: Get and inspect a template
    level = SovereigntyLevel.L3_HYBRID
    template = get_template(level)
    print(f"\nTemplate for L{level.value} ({level.name}):")
    print(f"  CPU cores: {template.compute.cpu_cores}")
    print(f"  Memory: {template.compute.memory_gb}GB")
    print(f"  GPU required: {template.compute.gpu_required}")
    print(f"  Air-gapped: {template.network.air_gapped}")
    print(f"  Storage encrypted: {template.storage.encrypted}")
    print(f"  Security controls: {template.security.key_management}")

    # Step 3: Package an agent for deployment
    packager = DeploymentPackager(level=level)
    package = packager.create_package(
        agent_id="analysis-agent-v2",
        model_ids=["local-llm-7b", "local-embedder-v1"],
        config={"max_tokens": 4096, "quantization": "int8"},
        target_region="eu-west-1",
    )
    print(f"\nDeployment package: {package.package_id}")
    print(f"  Manifest version: {package.manifest.version}")
    print(f"  Models: {package.manifest.model_ids}")
    print(f"  Target: {package.manifest.target_region}")

    # Step 4: Validate deployment configuration
    validator = DeploymentValidator(level=level)
    configs = [
        DeploymentConfig(
            encrypted_storage=True,
            network_isolated=True,
            audit_logging=True,
            region="eu-west-1",
        ),
        DeploymentConfig(
            encrypted_storage=False,  # missing requirement
            network_isolated=True,
            audit_logging=True,
            region="us-east-1",
        ),
    ]

    print("\nDeployment config validation:")
    for i, config in enumerate(configs):
        result = validator.validate(config)
        print(f"  Config {i + 1}: {result.status.value}")
        for issue in result.issues:
            print(f"    - {issue}")


if __name__ == "__main__":
    main()
