#!/usr/bin/env python3
"""Example: Quickstart — agent-sovereign

Minimal working example: assess sovereignty level, get a deployment
template, and run a compliance check.

Usage:
    python examples/01_quickstart.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    Bundler,
    SovereigntyAssessor,
    SovereigntyLevel,
    get_template,
    SovereigntyComplianceChecker,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Assess sovereignty level based on data types and regulations
    assessor = SovereigntyAssessor()
    assessment = assessor.assess(
        data_types=["pii", "financial"],
        regulations=["GDPR", "PCI-DSS"],
    )
    print(f"Sovereignty assessment:")
    print(f"  Level: {assessment.level.value} — {assessment.level.name}")
    print(f"  Rationale: {assessment.rationale[:70]}")

    # Step 2: Get deployment template for assessed level
    template = get_template(assessment.level)
    print(f"\nDeployment template for {assessment.level.name}:")
    print(f"  Compute: {template.compute.cpu_cores} cores, "
          f"{template.compute.memory_gb}GB RAM")
    print(f"  Network: {template.network.air_gapped}")
    print(f"  Storage: encrypted={template.storage.encrypted}")

    # Step 3: Bundle agent for deployment
    bundler = Bundler(level=assessment.level)
    bundle = bundler.bundle(
        agent_id="financial-analysis-agent",
        model_ids=["local-llm-v1"],
        config={"max_tokens": 2048, "temperature": 0.1},
    )
    print(f"\nBundle created: {bundle.bundle_id}")
    print(f"  Agent: {bundle.agent_id}")
    print(f"  Level: {bundle.sovereignty_level.value}")

    # Step 4: Compliance check
    checker = SovereigntyComplianceChecker()
    report = checker.check(
        level=assessment.level,
        deployment_region="eu-west-1",
        data_types=["pii", "financial"],
    )
    print(f"\nCompliance report:")
    print(f"  Status: {report.status.value}")
    print(f"  Issues: {len(report.issues)}")
    for issue in report.issues:
        print(f"    [{issue.severity}] {issue.description[:60]}")


if __name__ == "__main__":
    main()
