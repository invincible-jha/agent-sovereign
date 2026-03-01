#!/usr/bin/env python3
"""Example: Data Residency and Jurisdiction Mapping

Demonstrates setting data residency policies, mapping jurisdictions
to requirements, and checking compliance.

Usage:
    python examples/06_data_residency.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    DataResidencyPolicy,
    JurisdictionMapper,
    JurisdictionRequirements,
    ResidencyChecker,
    SovereigntyLevel,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Map jurisdictions to their requirements
    mapper = JurisdictionMapper()
    jurisdictions = ["EU", "US", "UK", "India", "Australia"]

    print("Jurisdiction requirements:")
    for jurisdiction in jurisdictions:
        requirements: JurisdictionRequirements = mapper.get(jurisdiction)
        print(f"  {jurisdiction}: "
              f"local_storage={requirements.requires_local_storage}, "
              f"data_export_restricted={requirements.data_export_restricted}, "
              f"min_level=L{requirements.minimum_sovereignty_level.value}")

    # Step 2: Define a data residency policy
    policy = DataResidencyPolicy(
        allowed_regions=["eu-west-1", "eu-central-1"],
        restricted_data_types=["pii", "phi"],
        requires_encryption_at_rest=True,
        requires_encryption_in_transit=True,
        audit_logging_required=True,
    )
    print(f"\nData residency policy:")
    print(f"  Allowed regions: {policy.allowed_regions}")
    print(f"  Restricted types: {policy.restricted_data_types}")

    # Step 3: Check residency compliance
    checker = ResidencyChecker(policy=policy)
    test_cases = [
        {
            "region": "eu-west-1",
            "data_type": "pii",
            "encrypted": True,
            "audited": True,
        },
        {
            "region": "us-east-1",  # not in allowed regions
            "data_type": "pii",
            "encrypted": True,
            "audited": True,
        },
        {
            "region": "eu-central-1",
            "data_type": "pii",
            "encrypted": False,  # missing encryption
            "audited": True,
        },
    ]

    print("\nResidency compliance checks:")
    for case in test_cases:
        result = checker.check(
            region=str(case["region"]),
            data_type=str(case["data_type"]),
            encrypted=bool(case["encrypted"]),
            audited=bool(case["audited"]),
        )
        status = "PASS" if result.compliant else "FAIL"
        print(f"  [{status}] region={case['region']}, "
              f"data={case['data_type']}")
        if not result.compliant:
            print(f"    Reason: {result.reason}")


if __name__ == "__main__":
    main()
