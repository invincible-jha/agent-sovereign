"""CLI entry point for agent-sovereign.

Invoked as::

    agent-sovereign [OPTIONS] COMMAND [ARGS]...

or, during development::

    python -m agent_sovereign.cli.main

Commands
--------
- ``assess``       Assess the sovereignty level for a workload.
- ``package``      Package a deployment bundle for a sovereignty level.
- ``validate``     Validate a deployment configuration against templates.
- ``provenance``   Record or inspect model provenance records.
- ``compliance``   Run a full sovereignty compliance check.
- ``edge-config``  Validate and estimate performance for an edge configuration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group()
@click.version_option()
def cli() -> None:
    """Sovereign and edge deployment toolkit for self-contained agent bundles"""


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.command(name="version")
def version_command() -> None:
    """Show detailed version information."""
    from agent_sovereign import __version__

    console.print(f"[bold]agent-sovereign[/bold] v{__version__}")


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------


@cli.command(name="plugins")
def plugins_command() -> None:
    """List all registered plugins loaded from entry-points."""
    console.print("[bold]Registered plugins:[/bold]")
    console.print("  (No plugins registered. Install a plugin package to see entries here.)")


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------


@cli.command(name="assess")
@click.option(
    "--data-types",
    "-d",
    multiple=True,
    help="Data type keys present in the workload (e.g. phi, financial_data). Repeatable.",
)
@click.option(
    "--regulations",
    "-r",
    multiple=True,
    help="Applicable regulation identifiers (e.g. HIPAA, GDPR). Repeatable.",
)
@click.option(
    "--geography",
    "-g",
    default=None,
    help="Deployment geography code (e.g. EU, US, CN).",
)
@click.option(
    "--org-minimum",
    "-m",
    default=1,
    type=click.IntRange(1, 7),
    help="Organisational minimum sovereignty level score (1–7). Default: 1.",
    show_default=True,
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def assess_command(
    data_types: tuple[str, ...],
    regulations: tuple[str, ...],
    geography: str | None,
    org_minimum: int,
    json_output: bool,
) -> None:
    """Assess the minimum sovereignty level for a workload.

    Examples:

    \b
        sovereign assess --data-types phi --regulations HIPAA --geography US
        sovereign assess -d classified -d itar_technical_data -r ITAR
        sovereign assess --data-types financial_data --regulations GDPR -g EU
    """
    from agent_sovereign.classifier.assessor import SovereigntyAssessor
    from agent_sovereign.classifier.levels import SovereigntyLevel

    org_level = SovereigntyLevel(org_minimum)
    assessor = SovereigntyAssessor(org_minimum=org_level)

    assessment = assessor.assess(
        data_types=list(data_types),
        regulations=list(regulations),
        geography=geography,
    )

    if json_output:
        output = {
            "level": assessment.level.name,
            "score": assessment.score,
            "justification": assessment.justification,
            "data_sensitivity": assessment.data_sensitivity,
            "regulatory_drivers": {
                reg: level.name for reg, level in assessment.regulatory_drivers.items()
            },
            "deployment_template": assessment.deployment_template,
            "warnings": assessment.warnings,
            "capability_requirements": assessment.capability_requirements,
        }
        console.print_json(json.dumps(output, indent=2))
        return

    console.print(
        Panel(
            f"[bold green]{assessment.level.name}[/bold green] (score {assessment.score}/7)",
            title="Sovereignty Assessment Result",
            expand=False,
        )
    )
    console.print(f"\n[bold]Justification:[/bold] {assessment.justification}\n")

    if assessment.regulatory_drivers:
        table = Table(title="Regulatory Drivers", show_header=True)
        table.add_column("Regulation", style="cyan")
        table.add_column("Required Level", style="yellow")
        for reg, level in assessment.regulatory_drivers.items():
            table.add_row(reg, level.name)
        console.print(table)

    if assessment.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in assessment.warnings:
            console.print(f"  [yellow]![/yellow] {warning}")

    console.print(
        f"\n[dim]Recommended deployment template:[/dim] {assessment.deployment_template}"
    )


# ---------------------------------------------------------------------------
# package
# ---------------------------------------------------------------------------


@cli.command(name="package")
@click.option(
    "--level",
    "-l",
    required=True,
    type=click.IntRange(1, 7),
    help="Target sovereignty level (1–7).",
)
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Directory to package. Mutually exclusive with --files.",
)
@click.option(
    "--files",
    "-f",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Explicit files to include. Repeatable. Mutually exclusive with --source-dir.",
)
@click.option(
    "--package-id",
    default=None,
    help="Override the auto-generated package ID.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the manifest YAML to this file path.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output summary as JSON.",
)
def package_command(
    level: int,
    source_dir: Path | None,
    files: tuple[Path, ...],
    package_id: str | None,
    output: Path | None,
    json_output: bool,
) -> None:
    """Package a deployment bundle for a given sovereignty level.

    Examples:

    \b
        sovereign package --level 3 --source-dir ./my-agent/
        sovereign package --level 5 --files model.gguf --files config.yaml
        sovereign package -l 4 -s ./bundle/ -o manifest.yaml
    """
    from agent_sovereign.classifier.levels import SovereigntyLevel
    from agent_sovereign.deployment.packager import DeploymentPackager

    sovereignty_level = SovereigntyLevel(level)
    packager = DeploymentPackager(
        sovereignty_level=sovereignty_level,
        package_id=package_id,
    )

    if source_dir is None and not files:
        console.print(
            "[red]Error:[/red] Provide either --source-dir or one or more --files arguments."
        )
        sys.exit(1)
    if source_dir is not None and files:
        console.print("[red]Error:[/red] --source-dir and --files are mutually exclusive.")
        sys.exit(1)

    try:
        package = packager.package(
            source_directory=source_dir,
            explicit_files=list(files) if files else None,
        )
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Packaging error:[/red] {exc}")
        sys.exit(1)

    if output is not None:
        output.write_text(package.manifest_yaml, encoding="utf-8")
        console.print(f"[green]Manifest written to:[/green] {output}")

    if json_output:
        summary = {
            "package_id": package.manifest.package_id,
            "sovereignty_level": package.sovereignty_level.name,
            "template_name": package.template.name,
            "file_count": len(package.files_list),
            "checksum": package.checksum,
            "created_at": package.manifest.created_at,
        }
        console.print_json(json.dumps(summary, indent=2))
        return

    console.print(
        Panel(
            f"[bold green]{package.manifest.package_id}[/bold green]",
            title="Deployment Package Created",
            expand=False,
        )
    )
    console.print(f"  Sovereignty level : {package.sovereignty_level.name}")
    console.print(f"  Template          : {package.template.name}")
    console.print(f"  Files included    : {len(package.files_list)}")
    console.print(f"  Checksum (SHA-256): {package.checksum}")
    console.print(f"  Created at        : {package.manifest.created_at}")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@cli.command(name="validate")
@click.option(
    "--level",
    "-l",
    required=True,
    type=click.IntRange(1, 7),
    help="Claimed sovereignty level of the deployment (1–7).",
)
@click.option(
    "--region",
    "-r",
    default="",
    help="Data residency region code (e.g. US, DE, CN).",
)
@click.option(
    "--network-isolated",
    is_flag=True,
    default=False,
    help="Set if the deployment is network-isolated.",
)
@click.option(
    "--encryption-at-rest",
    default="",
    help="Encryption standard for data at rest (e.g. AES-256-HSM).",
)
@click.option(
    "--encryption-in-transit",
    default="",
    help="Encryption standard for data in transit (e.g. mTLS).",
)
@click.option(
    "--key-management",
    default="",
    help="Key management approach (e.g. local_hsm, provider_managed).",
)
@click.option(
    "--audit-logging",
    is_flag=True,
    default=False,
    help="Set if audit logging is enabled.",
)
@click.option(
    "--air-gapped",
    is_flag=True,
    default=False,
    help="Set if the deployment is truly air-gapped.",
)
@click.option(
    "--tpm",
    is_flag=True,
    default=False,
    help="Set if a Trusted Platform Module (TPM) is present.",
)
@click.option(
    "--fips-hardware",
    is_flag=True,
    default=False,
    help="Set if FIPS 140-2 validated hardware is in use.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def validate_command(
    level: int,
    region: str,
    network_isolated: bool,
    encryption_at_rest: str,
    encryption_in_transit: str,
    key_management: str,
    audit_logging: bool,
    air_gapped: bool,
    tpm: bool,
    fips_hardware: bool,
    json_output: bool,
) -> None:
    """Validate a deployment configuration against sovereignty requirements.

    Examples:

    \b
        sovereign validate --level 3 --region DE --network-isolated \\
            --encryption-at-rest AES-256-HSM --encryption-in-transit mTLS \\
            --key-management local_hsm --audit-logging

        sovereign validate --level 4 --air-gapped --tpm --fips-hardware \\
            --encryption-at-rest FIPS-140-2-L2 --key-management local_hsm
    """
    from agent_sovereign.classifier.levels import SovereigntyLevel
    from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator, ValidationStatus

    sovereignty_level = SovereigntyLevel(level)
    config = DeploymentConfig(
        sovereignty_level=sovereignty_level,
        data_residency_region=region,
        network_isolated=network_isolated,
        encryption_at_rest=encryption_at_rest,
        encryption_in_transit=encryption_in_transit,
        key_management=key_management,
        audit_logging_enabled=audit_logging,
        air_gapped=air_gapped,
        tpm_present=tpm,
        fips_hardware=fips_hardware,
    )
    validator = DeploymentValidator()
    results = validator.validate(config)

    if json_output:
        output = [
            {
                "check_id": r.check_id,
                "status": r.status.value,
                "message": r.message,
                "requirement": r.requirement,
                "actual": r.actual,
            }
            for r in results
        ]
        failed = [r for r in results if r.status == ValidationStatus.FAILED]
        console.print_json(
            json.dumps(
                {"overall": "FAILED" if failed else "PASSED", "checks": output},
                indent=2,
            )
        )
        sys.exit(1 if failed else 0)

    table = Table(title=f"Validation Results — {sovereignty_level.name}", show_header=True)
    table.add_column("Check", style="cyan", min_width=22)
    table.add_column("Status", min_width=10)
    table.add_column("Message")

    failed_count = 0
    for result in results:
        if result.status == ValidationStatus.PASSED:
            status_str = "[green]PASSED[/green]"
        elif result.status == ValidationStatus.FAILED:
            status_str = "[red]FAILED[/red]"
            failed_count += 1
        elif result.status == ValidationStatus.WARNING:
            status_str = "[yellow]WARNING[/yellow]"
        else:
            status_str = "[dim]SKIPPED[/dim]"
        table.add_row(result.check_id, status_str, result.message)

    console.print(table)

    if failed_count:
        console.print(
            f"\n[red]Validation FAILED:[/red] {failed_count} check(s) did not pass."
        )
        sys.exit(1)
    else:
        console.print("\n[green]All checks PASSED.[/green]")


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


@cli.command(name="provenance")
@click.option(
    "--model-id",
    "-m",
    required=True,
    help="Unique model identifier (URN, hash, or label).",
)
@click.option(
    "--source",
    "-s",
    default="",
    help="Model origin URI or description.",
)
@click.option(
    "--version",
    "-v",
    "model_version",
    default="1.0.0",
    help="Model version string.",
    show_default=True,
)
@click.option(
    "--training-data",
    "-t",
    multiple=True,
    help="Training data source identifiers. Repeatable.",
)
@click.option(
    "--certifications",
    "-c",
    multiple=True,
    help="Certification or audit identifiers. Repeatable.",
)
@click.option(
    "--parent-model-id",
    default=None,
    help="Parent model ID for fine-tuned or derived models.",
)
@click.option(
    "--attest",
    is_flag=True,
    default=False,
    help="Generate an HMAC attestation for the provenance record.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def provenance_command(
    model_id: str,
    source: str,
    model_version: str,
    training_data: tuple[str, ...],
    certifications: tuple[str, ...],
    parent_model_id: str | None,
    attest: bool,
    json_output: bool,
) -> None:
    """Record and display model provenance information.

    Examples:

    \b
        sovereign provenance --model-id llama-3-8b-instruct --source hf://meta/llama3 \\
            --version 1.0.0 --training-data CommonCrawl --certifications ISO-42001

        sovereign provenance -m my-finetune --parent-model-id llama-3-8b-instruct \\
            --source internal --version 0.2.1 --attest
    """
    import secrets as secrets_module

    from agent_sovereign.provenance.attestation import AttestationGenerator
    from agent_sovereign.provenance.tracker import ModelProvenance, ProvenanceTracker

    tracker = ProvenanceTracker()
    provenance = ModelProvenance(
        model_id=model_id,
        source=source,
        version=model_version,
        training_data_sources=list(training_data),
        certifications=list(certifications),
        parent_model_id=parent_model_id or None,
    )
    tracker.record(provenance)

    attestation = None
    if attest:
        key = secrets_module.token_bytes(32)
        generator = AttestationGenerator(secret_key=key)
        attestation = generator.generate(provenance)

    if json_output:
        output: dict[str, object] = {
            "model_id": provenance.model_id,
            "source": provenance.source,
            "version": provenance.version,
            "training_data_sources": provenance.training_data_sources,
            "certifications": provenance.certifications,
            "recorded_at": provenance.recorded_at,
            "parent_model_id": provenance.parent_model_id,
        }
        if attestation is not None:
            output["attestation"] = {
                "attestation_id": attestation.attestation_id,
                "issued_at": attestation.issued_at,
                "expires_at": attestation.expires_at,
                "signature": attestation.signature,
                "algorithm": attestation.algorithm,
            }
        console.print_json(json.dumps(output, indent=2))
        return

    console.print(
        Panel(
            f"[bold]{provenance.model_id}[/bold]  v{provenance.version}",
            title="Provenance Record",
            expand=False,
        )
    )
    console.print(f"  Source            : {provenance.source or '(not specified)'}")
    console.print(f"  Recorded at       : {provenance.recorded_at}")
    console.print(f"  Parent model      : {provenance.parent_model_id or 'none (root)'}")
    console.print(f"  Training datasets : {', '.join(provenance.training_data_sources) or 'none'}")
    console.print(f"  Certifications    : {', '.join(provenance.certifications) or 'none'}")

    if attestation is not None:
        console.print("\n[bold green]Attestation generated:[/bold green]")
        console.print(f"  ID        : {attestation.attestation_id}")
        console.print(f"  Algorithm : {attestation.algorithm}")
        console.print(f"  Issued    : {attestation.issued_at}")
        console.print(f"  Expires   : {attestation.expires_at}")
        console.print(f"  Signature : {attestation.signature[:32]}...")
        console.print(
            "\n[yellow]Note:[/yellow] The signing key was generated ephemerally for this "
            "session and is not persisted. In production, supply a stable key."
        )


# ---------------------------------------------------------------------------
# compliance
# ---------------------------------------------------------------------------


@cli.command(name="compliance")
@click.option(
    "--level",
    "-l",
    required=True,
    type=click.IntRange(1, 7),
    help="Claimed sovereignty level of the deployment (1–7).",
)
@click.option(
    "--region",
    "-r",
    default="",
    help="Data residency region code (e.g. DE, US, BR).",
)
@click.option(
    "--network-isolated",
    is_flag=True,
    default=False,
    help="Set if the deployment is network-isolated.",
)
@click.option(
    "--encryption-at-rest",
    default="",
    help="Encryption standard for data at rest.",
)
@click.option(
    "--encryption-in-transit",
    default="",
    help="Encryption standard for data in transit.",
)
@click.option(
    "--key-management",
    default="",
    help="Key management approach.",
)
@click.option(
    "--audit-logging",
    is_flag=True,
    default=False,
    help="Set if audit logging is enabled.",
)
@click.option(
    "--air-gapped",
    is_flag=True,
    default=False,
    help="Set if the deployment is truly air-gapped.",
)
@click.option(
    "--tpm",
    is_flag=True,
    default=False,
    help="Set if a TPM is present.",
)
@click.option(
    "--fips-hardware",
    is_flag=True,
    default=False,
    help="Set if FIPS 140-2 validated hardware is in use.",
)
@click.option(
    "--policy-allowed-regions",
    multiple=True,
    help="Allowed regions for the residency policy check. Repeatable.",
)
@click.option(
    "--policy-blocked-regions",
    multiple=True,
    help="Blocked regions for the residency policy check. Repeatable.",
)
@click.option(
    "--deployment-id",
    default="cli-deployment",
    help="Label for this deployment in the report.",
    show_default=True,
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def compliance_command(
    level: int,
    region: str,
    network_isolated: bool,
    encryption_at_rest: str,
    encryption_in_transit: str,
    key_management: str,
    audit_logging: bool,
    air_gapped: bool,
    tpm: bool,
    fips_hardware: bool,
    policy_allowed_regions: tuple[str, ...],
    policy_blocked_regions: tuple[str, ...],
    deployment_id: str,
    json_output: bool,
) -> None:
    """Run a full sovereignty compliance check for a deployment.

    Examples:

    \b
        sovereign compliance --level 3 --region DE \\
            --network-isolated --encryption-at-rest AES-256-HSM \\
            --encryption-in-transit mTLS --key-management local_hsm \\
            --audit-logging --policy-allowed-regions EU

        sovereign compliance -l 1 --region US --encryption-at-rest AES-256 \\
            --encryption-in-transit TLS-1.3 --key-management provider_managed
    """
    from agent_sovereign.classifier.levels import SovereigntyLevel
    from agent_sovereign.compliance.checker import SovereigntyComplianceChecker
    from agent_sovereign.deployment.validator import DeploymentConfig
    from agent_sovereign.residency.policy import DataResidencyPolicy

    sovereignty_level = SovereigntyLevel(level)
    config = DeploymentConfig(
        sovereignty_level=sovereignty_level,
        data_residency_region=region,
        network_isolated=network_isolated,
        encryption_at_rest=encryption_at_rest,
        encryption_in_transit=encryption_in_transit,
        key_management=key_management,
        audit_logging_enabled=audit_logging,
        air_gapped=air_gapped,
        tpm_present=tpm,
        fips_hardware=fips_hardware,
    )

    policies: list[DataResidencyPolicy] = []
    if policy_allowed_regions or policy_blocked_regions:
        policies.append(
            DataResidencyPolicy(
                policy_id="cli-residency-policy",
                allowed_regions=list(policy_allowed_regions),
                blocked_regions=list(policy_blocked_regions),
                description="Policy constructed from CLI arguments.",
            )
        )

    checker = SovereigntyComplianceChecker(residency_policies=policies)
    report = checker.check(deployment=config, deployment_id=deployment_id)

    if json_output:
        output = {
            "deployment_id": report.deployment_id,
            "assessed_at": report.assessed_at,
            "sovereignty_level": report.sovereignty_level.name,
            "overall_status": report.overall_status.value,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "warnings": report.warnings,
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "severity": i.severity,
                    "description": i.description,
                    "remediation": i.remediation,
                }
                for i in report.issues
            ],
            "jurisdiction_summary": report.jurisdiction_summary,
        }
        console.print_json(json.dumps(output, indent=2))
        sys.exit(0 if report.is_compliant else 1)

    status_colour = "green" if report.is_compliant else "red"
    console.print(
        Panel(
            f"[bold {status_colour}]{report.overall_status.value.upper()}[/bold {status_colour}]  "
            f"— {sovereignty_level.name}",
            title=f"Compliance Report: {report.deployment_id}",
            expand=False,
        )
    )
    console.print(f"  Assessed at : {report.assessed_at}")
    console.print(
        f"  Passed      : [green]{len(report.passed_checks)}[/green]  "
        f"Failed: [red]{len(report.failed_checks)}[/red]  "
        f"Warnings: [yellow]{len(report.warnings)}[/yellow]"
    )

    if report.issues:
        console.print("\n[bold red]Issues:[/bold red]")
        for issue in report.issues:
            sev_colour = "red" if issue.severity == "critical" else "yellow"
            console.print(
                f"  [{sev_colour}][{issue.severity.upper()}][/{sev_colour}] "
                f"{issue.issue_id}: {issue.description}"
            )
            console.print(f"    [dim]Remediation:[/dim] {issue.remediation}")

    if report.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in report.warnings:
            console.print(f"  [yellow]![/yellow] {warning}")

    if report.jurisdiction_summary:
        console.print("\n[bold]Jurisdiction Summary:[/bold]")
        for jurisdiction, summary in report.jurisdiction_summary.items():
            console.print(f"  [cyan]{jurisdiction}:[/cyan] {summary}")

    sys.exit(0 if report.is_compliant else 1)


# ---------------------------------------------------------------------------
# edge-config
# ---------------------------------------------------------------------------


@cli.command(name="edge-config")
@click.option(
    "--max-memory-mb",
    required=True,
    type=int,
    help="Maximum RAM available in MiB.",
)
@click.option(
    "--max-cpu-percent",
    default=80.0,
    type=float,
    help="Maximum CPU utilisation percentage (0–100).",
    show_default=True,
)
@click.option(
    "--quantization",
    type=click.Choice(
        ["none", "int8", "int4", "gguf_q4_k_m", "gguf_q5_k_m", "gguf_q8_0"],
        case_sensitive=False,
    ),
    default="none",
    help="Model quantization level.",
    show_default=True,
)
@click.option(
    "--offline-capable",
    is_flag=True,
    default=False,
    help="Set if the edge node can operate offline.",
)
@click.option(
    "--gpu-memory-mb",
    default=0,
    type=int,
    help="GPU memory available in MiB (0 = no GPU).",
    show_default=True,
)
@click.option(
    "--max-concurrent-requests",
    default=1,
    type=int,
    help="Maximum simultaneous inference requests.",
    show_default=True,
)
@click.option(
    "--model-size-b",
    default=7.0,
    type=float,
    help="Model size in billions of parameters for performance estimation.",
    show_default=True,
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def edge_config_command(
    max_memory_mb: int,
    max_cpu_percent: float,
    quantization: str,
    offline_capable: bool,
    gpu_memory_mb: int,
    max_concurrent_requests: int,
    model_size_b: float,
    json_output: bool,
) -> None:
    """Validate edge hardware resources and estimate inference performance.

    Examples:

    \b
        sovereign edge-config --max-memory-mb 8192 --quantization gguf_q4_k_m \\
            --model-size-b 7.0 --offline-capable

        sovereign edge-config --max-memory-mb 32768 --gpu-memory-mb 16384 \\
            --quantization int8 --model-size-b 13.0 --max-cpu-percent 60
    """
    from agent_sovereign.edge.runtime import EdgeConfig, EdgeRuntime, QuantizationLevel

    quant_level = QuantizationLevel(quantization.lower())
    config = EdgeConfig(
        max_memory_mb=max_memory_mb,
        max_cpu_percent=max_cpu_percent,
        model_quantization=quant_level,
        offline_capable=offline_capable,
        gpu_memory_mb=gpu_memory_mb,
        max_concurrent_requests=max_concurrent_requests,
    )
    runtime = EdgeRuntime(config)
    validation = runtime.validate_resources()
    estimate = runtime.estimate_performance(model_size_b)

    if json_output:
        output = {
            "validation": {
                "is_valid": validation.is_valid,
                "available_memory_mb": validation.available_memory_mb,
                "available_cpu_count": validation.available_cpu_count,
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
            "performance_estimate": {
                "tokens_per_second": estimate.tokens_per_second,
                "time_to_first_token_ms": estimate.time_to_first_token_ms,
                "max_context_tokens": estimate.max_context_tokens,
                "quantization_speedup_factor": estimate.quantization_speedup_factor,
                "notes": estimate.notes,
            },
        }
        console.print_json(json.dumps(output, indent=2))
        sys.exit(0 if validation.is_valid else 1)

    valid_str = "[green]VALID[/green]" if validation.is_valid else "[red]INVALID[/red]"
    console.print(
        Panel(
            f"Resource validation: {valid_str}",
            title="Edge Configuration",
            expand=False,
        )
    )
    console.print(f"  Config memory     : {max_memory_mb} MiB")
    console.print(f"  Available memory  : {validation.available_memory_mb} MiB")
    console.print(f"  CPU cores         : {validation.available_cpu_count}")
    console.print(f"  GPU memory        : {gpu_memory_mb} MiB")
    console.print(f"  Quantization      : {quantization}")
    console.print(f"  Offline capable   : {offline_capable}")

    if validation.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in validation.errors:
            console.print(f"  [red]x[/red] {error}")

    if validation.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in validation.warnings:
            console.print(f"  [yellow]![/yellow] {warning}")

    console.print("\n[bold]Performance Estimate[/bold] "
                  f"(model: {model_size_b}B params)")
    console.print(f"  Tokens/second         : {estimate.tokens_per_second:.1f}")
    console.print(f"  Time to first token   : {estimate.time_to_first_token_ms:.0f} ms")
    console.print(f"  Max context tokens    : {estimate.max_context_tokens:,}")
    console.print(f"  Quantization speedup  : {estimate.quantization_speedup_factor:.1f}x")

    if estimate.notes:
        console.print("\n[dim]Notes:[/dim]")
        for note in estimate.notes:
            console.print(f"  [dim]-[/dim] {note}")

    sys.exit(0 if validation.is_valid else 1)


if __name__ == "__main__":
    cli()
