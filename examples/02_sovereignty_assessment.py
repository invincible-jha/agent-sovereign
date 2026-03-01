#!/usr/bin/env python3
"""Example: Sovereignty Level Assessment

Demonstrates the full sovereignty classification pipeline including
data sensitivity detection, regulatory mapping, and level assignment.

Usage:
    python examples/02_sovereignty_assessment.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    DATA_SENSITIVITY,
    DataSensitivityDetector,
    REGULATORY_MINIMUMS,
    RegulatoryMapper,
    SovereigntyAssessor,
    SovereigntyLevel,
    get_level_description,
    get_capability_requirements,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Data sensitivity detection
    detector = DataSensitivityDetector()
    sample_texts = [
        "The user's social security number is 123-45-6789.",
        "Q3 revenue was $12.4M, up 18% year-over-year.",
        "Patient diagnosis: hypertension, prescribed lisinopril.",
        "Public announcement: new product launch in March.",
    ]
    print("Data sensitivity detection:")
    for text in sample_texts:
        result = detector.detect(text[:60])
        print(f"  [{result.sensitivity_level}] {text[:55]}")

    # Step 2: Regulatory mapping
    mapper = RegulatoryMapper()
    regulations = ["GDPR", "HIPAA", "SOC2", "PCI-DSS"]
    print(f"\nRegulatory minimum sovereignty levels:")
    for reg in regulations:
        min_level = mapper.get_minimum_level(reg)
        print(f"  {reg}: L{min_level.value}")

    # Step 3: Full assessment for different profiles
    assessor = SovereigntyAssessor()
    profiles = [
        {
            "name": "Public chatbot",
            "data_types": ["general"],
            "regulations": [],
        },
        {
            "name": "HR assistant",
            "data_types": ["pii", "employment"],
            "regulations": ["GDPR"],
        },
        {
            "name": "Clinical decision support",
            "data_types": ["phi", "pii"],
            "regulations": ["HIPAA"],
        },
    ]

    print("\nSovereignty assessments:")
    for profile in profiles:
        assessment = assessor.assess(
            data_types=list(profile["data_types"]),  # type: ignore[arg-type]
            regulations=list(profile["regulations"]),  # type: ignore[arg-type]
        )
        desc = get_level_description(assessment.level)
        caps = get_capability_requirements(assessment.level)
        print(f"\n  {profile['name']}:")
        print(f"    Level: L{assessment.level.value} — {desc[:50]}")
        print(f"    Requires: {caps[:60]}")


if __name__ == "__main__":
    main()
