#!/usr/bin/env python3
"""Example: Sovereignty Compliance Reporting

Demonstrates full compliance checking across multiple regulations
and generating structured compliance reports.

Usage:
    python examples/07_compliance_reporting.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    ComplianceReport,
    ComplianceStatus,
    SovereigntyAssessor,
    SovereigntyComplianceChecker,
    SovereigntyLevel,
)


def print_report(report: ComplianceReport, label: str) -> None:
    print(f"\n{label}:")
    print(f"  Status: {report.status.value}")
    print(f"  Issues: {len(report.issues)}")
    for issue in report.issues:
        print(f"    [{issue.severity}] {issue.description[:70]}")
    if report.recommendations:
        print(f"  Recommendations ({len(report.recommendations)}):")
        for rec in report.recommendations[:2]:
            print(f"    - {rec[:70]}")


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    checker = SovereigntyComplianceChecker()

    # Scenario 1: Public cloud deployment (L1)
    report1 = checker.check(
        level=SovereigntyLevel.L1_CLOUD_STANDARD,
        deployment_region="us-east-1",
        data_types=["general", "aggregated"],
    )
    print_report(report1, "L1 Cloud Standard (public cloud, general data)")

    # Scenario 2: GDPR-regulated deployment (L3)
    report2 = checker.check(
        level=SovereigntyLevel.L3_HYBRID,
        deployment_region="eu-west-1",
        data_types=["pii"],
        regulations=["GDPR"],
    )
    print_report(report2, "L3 Hybrid (GDPR PII, EU region)")

    # Scenario 3: Healthcare on-premise (L4)
    report3 = checker.check(
        level=SovereigntyLevel.L4_LOCAL_AUGMENTED,
        deployment_region="on-premise",
        data_types=["phi", "pii"],
        regulations=["HIPAA"],
    )
    print_report(report3, "L4 Local (HIPAA PHI, on-premise)")

    # Summary comparison
    all_reports = [
        ("L1", report1),
        ("L3", report2),
        ("L4", report3),
    ]
    print(f"\nCompliance summary:")
    for label, report in all_reports:
        icon = "OK" if report.status == ComplianceStatus.COMPLIANT else "!!"
        print(f"  [{icon}] {label}: {report.status.value} "
              f"({len(report.issues)} issues)")


if __name__ == "__main__":
    main()
