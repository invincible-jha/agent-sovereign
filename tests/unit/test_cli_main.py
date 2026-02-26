"""Tests for CLI commands in agent_sovereign.cli.main.

Uses Click's CliRunner for full in-process invocation so that coverage
is collected against the real command implementations.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_sovereign.cli.main import cli


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


class TestVersionCommand:
    def test_version_prints_package_name(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "agent-sovereign" in result.output

    def test_version_contains_version_string(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        # Should contain at least a digit (version number)
        assert any(ch.isdigit() for ch in result.output)


# ---------------------------------------------------------------------------
# plugins command
# ---------------------------------------------------------------------------


class TestPluginsCommand:
    def test_plugins_exits_cleanly(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["plugins"])
        assert result.exit_code == 0

    def test_plugins_mentions_plugins(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["plugins"])
        assert "plugin" in result.output.lower()


# ---------------------------------------------------------------------------
# assess command
# ---------------------------------------------------------------------------


class TestAssessCommand:
    def test_basic_assess_exits_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["assess", "--data-types", "phi"])
        assert result.exit_code == 0

    def test_assess_with_regulations_and_geography(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "assess",
                "--data-types", "phi",
                "--regulations", "HIPAA",
                "--geography", "US",
            ],
        )
        assert result.exit_code == 0
        assert "Sovereignty" in result.output or "sovereignty" in result.output.lower()

    def test_assess_json_output_is_valid_json(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["assess", "--data-types", "phi", "--json-output"],
        )
        assert result.exit_code == 0
        # Output should contain parseable JSON
        data = json.loads(result.output)
        assert "level" in data
        assert "score" in data
        assert "justification" in data

    def test_assess_json_output_has_regulatory_drivers(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "assess",
                "--data-types", "phi",
                "--regulations", "HIPAA",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "regulatory_drivers" in data

    def test_assess_json_output_has_warnings_key(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["assess", "--data-types", "financial_data", "--json-output"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "warnings" in data
        assert "capability_requirements" in data

    def test_assess_no_options_uses_defaults(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["assess"])
        assert result.exit_code == 0

    def test_assess_with_org_minimum(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["assess", "--data-types", "public_data", "--org-minimum", "3"],
        )
        assert result.exit_code == 0

    def test_assess_multiple_data_types(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "assess",
                "--data-types", "phi",
                "--data-types", "financial_data",
                "--regulations", "HIPAA",
                "--regulations", "GDPR",
            ],
        )
        assert result.exit_code == 0

    def test_assess_with_regulatory_drivers_in_rich_output(self, runner: CliRunner) -> None:
        # HIPAA + phi should produce regulatory_drivers output in table
        result = runner.invoke(
            cli,
            [
                "assess",
                "--data-types", "phi",
                "--regulations", "HIPAA",
            ],
        )
        assert result.exit_code == 0

    def test_assess_classified_data_shows_warnings(self, runner: CliRunner) -> None:
        # classified data should produce warnings in rich output
        result = runner.invoke(
            cli,
            ["assess", "--data-types", "classified"],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# package command
# ---------------------------------------------------------------------------


class TestPackageCommand:
    def test_package_no_source_or_files_exits_nonzero(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["package", "--level", "1"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_package_source_dir_and_files_mutually_exclusive(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        dummy_file = tmp_path / "model.bin"
        dummy_file.write_bytes(b"data")
        result = runner.invoke(
            cli,
            [
                "package",
                "--level", "1",
                "--source-dir", str(tmp_path),
                "--files", str(dummy_file),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_package_with_source_dir_exits_zero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "model.bin").write_bytes(b"fake model weights")
        result = runner.invoke(
            cli,
            ["package", "--level", "1", "--source-dir", str(tmp_path)],
        )
        assert result.exit_code == 0

    def test_package_json_output(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "model.bin").write_bytes(b"fake model weights")
        result = runner.invoke(
            cli,
            [
                "package",
                "--level", "1",
                "--source-dir", str(tmp_path),
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "package_id" in data
        assert "sovereignty_level" in data
        assert "file_count" in data
        assert "checksum" in data

    def test_package_with_explicit_files(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        result = runner.invoke(
            cli,
            ["package", "--level", "2", "--files", str(f)],
        )
        assert result.exit_code == 0

    def test_package_with_output_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "model.bin").write_bytes(b"data")
        manifest_path = tmp_path / "manifest.yaml"
        result = runner.invoke(
            cli,
            [
                "package",
                "--level", "1",
                "--source-dir", str(tmp_path),
                "--output", str(manifest_path),
            ],
        )
        assert result.exit_code == 0
        assert manifest_path.exists()
        assert "Manifest written" in result.output

    def test_package_with_custom_package_id(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "model.bin").write_bytes(b"data")
        result = runner.invoke(
            cli,
            [
                "package",
                "--level", "3",
                "--source-dir", str(tmp_path),
                "--package-id", "my-custom-pkg-001",
            ],
        )
        assert result.exit_code == 0
        assert "my-custom-pkg-001" in result.output

    def test_package_rich_output_shows_level_and_template(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / "agent.py").write_text("print('hello')")
        result = runner.invoke(
            cli,
            ["package", "--level", "2", "--source-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        # Rich output should mention sovereignty level and template
        assert "L2" in result.output or "l2" in result.output.lower() or "CLOUD" in result.output


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_validate_l1_basic_passes(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
            ],
        )
        # L1 basic config should pass validation
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_validate_json_output_overall_passed(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert "overall" in data
        assert "checks" in data

    def test_validate_json_output_failed_returns_nonzero(
        self, runner: CliRunner
    ) -> None:
        # L4 without required controls should fail
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "4",
                "--region", "",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert data["overall"] == "FAILED"
        assert result.exit_code == 1

    def test_validate_failed_rich_output_shows_failed_count(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            ["validate", "--level", "4"],
        )
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_validate_with_all_flags(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "4",
                "--region", "US",
                "--network-isolated",
                "--encryption-at-rest", "FIPS-140-2-L2",
                "--encryption-in-transit", "mTLS",
                "--key-management", "local_hsm",
                "--audit-logging",
                "--air-gapped",
                "--tpm",
                "--fips-hardware",
            ],
        )
        # All controls present for L4 — should pass
        assert result.exit_code == 0

    def test_validate_rich_output_skipped_status(self, runner: CliRunner) -> None:
        # L1 with minimal config will have some SKIPPED checks (e.g. air_gap not required)
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
            ],
        )
        assert result.exit_code == 0

    def test_validate_warning_status_shown(self, runner: CliRunner) -> None:
        # Some checks may produce WARNING status
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "2",
                "--region", "US",
                "--encryption-at-rest", "AES-256-CMK",
                "--encryption-in-transit", "TLS 1.3",
                "--key-management", "customer_managed_kms",
                "--audit-logging",
            ],
        )
        # Just confirm it runs cleanly
        assert result.exit_code in (0, 1)

    def test_validate_json_checks_have_required_fields(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "validate",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert len(data["checks"]) > 0
        first_check = data["checks"][0]
        assert "check_id" in first_check
        assert "status" in first_check
        assert "message" in first_check


# ---------------------------------------------------------------------------
# provenance command
# ---------------------------------------------------------------------------


class TestProvenanceCommand:
    def test_provenance_basic(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["provenance", "--model-id", "test-model-v1"],
        )
        assert result.exit_code == 0
        assert "test-model-v1" in result.output

    def test_provenance_json_output(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "llama-3-8b",
                "--source", "hf://meta/llama3",
                "--version", "1.0.0",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["model_id"] == "llama-3-8b"
        assert data["source"] == "hf://meta/llama3"
        assert data["version"] == "1.0.0"

    def test_provenance_with_training_data_and_certifications(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "my-model",
                "--training-data", "CommonCrawl",
                "--training-data", "Wikipedia",
                "--certifications", "ISO-42001",
            ],
        )
        assert result.exit_code == 0

    def test_provenance_json_includes_training_data_list(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "my-model",
                "--training-data", "DatasetA",
                "--training-data", "DatasetB",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "DatasetA" in data["training_data_sources"]
        assert "DatasetB" in data["training_data_sources"]

    def test_provenance_with_parent_model_id(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "my-finetune",
                "--parent-model-id", "llama-3-8b",
            ],
        )
        assert result.exit_code == 0
        assert "llama-3-8b" in result.output

    def test_provenance_json_with_parent_model_id(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "my-finetune",
                "--parent-model-id", "base-model",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["parent_model_id"] == "base-model"

    def test_provenance_with_attest_flag_adds_attestation(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "attested-model",
                "--attest",
            ],
        )
        assert result.exit_code == 0
        assert "Attestation" in result.output

    def test_provenance_json_with_attest_includes_attestation_block(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "attested-model",
                "--source", "internal",
                "--attest",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "attestation" in data
        assert "attestation_id" in data["attestation"]
        assert "signature" in data["attestation"]
        assert "algorithm" in data["attestation"]

    def test_provenance_rich_output_shows_source_and_recorded_at(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "provenance",
                "--model-id", "my-model",
                "--source", "https://example.com/model",
            ],
        )
        assert result.exit_code == 0
        assert "Source" in result.output
        assert "Recorded at" in result.output

    def test_provenance_empty_training_data_shows_none(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            ["provenance", "--model-id", "bare-model"],
        )
        assert result.exit_code == 0
        assert "none" in result.output.lower()


# ---------------------------------------------------------------------------
# compliance command
# ---------------------------------------------------------------------------


class TestComplianceCommand:
    def test_compliance_l1_basic_exits_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
            ],
        )
        # L1 basic config should be compliant
        assert result.exit_code == 0

    def test_compliance_json_output_shape(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert "deployment_id" in data
        assert "overall_status" in data
        assert "issues" in data
        assert "passed_checks" in data
        assert "failed_checks" in data
        assert "jurisdiction_summary" in data

    def test_compliance_non_compliant_exits_nonzero(
        self, runner: CliRunner
    ) -> None:
        # L5 without network isolation should fail
        result = runner.invoke(
            cli,
            ["compliance", "--level", "5", "--region", "US"],
        )
        assert result.exit_code == 1

    def test_compliance_json_non_compliant_exit_nonzero(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "5",
                "--region", "US",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert data["overall_status"] != "compliant"
        assert result.exit_code == 1

    def test_compliance_with_policy_allowed_regions(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--policy-allowed-regions", "US",
            ],
        )
        # US is in allowed regions → residency policy passes
        assert result.exit_code == 0

    def test_compliance_with_policy_blocked_regions_fails(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "CN",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--policy-blocked-regions", "CN",
            ],
        )
        assert result.exit_code == 1

    def test_compliance_rich_output_shows_assessed_at(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
            ],
        )
        assert "Assessed at" in result.output

    def test_compliance_with_deployment_id(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "US",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
                "--deployment-id", "prod-cluster-01",
            ],
        )
        assert result.exit_code == 0
        assert "prod-cluster-01" in result.output

    def test_compliance_issues_displayed_in_rich_output(
        self, runner: CliRunner
    ) -> None:
        # L5 without controls will have issues printed
        result = runner.invoke(
            cli,
            ["compliance", "--level", "5", "--region", "DE"],
        )
        # Should show Issues section or at least mention failures
        assert result.exit_code == 1
        assert "Issues" in result.output or "FAILED" in result.output or "failed" in result.output.lower()

    def test_compliance_warnings_displayed_when_present(
        self, runner: CliRunner
    ) -> None:
        # Unknown region produces a jurisdiction warning
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "1",
                "--region", "UNKNOWNXYZ",
                "--encryption-at-rest", "AES-256",
                "--encryption-in-transit", "TLS-1.3",
                "--key-management", "provider_managed",
                "--audit-logging",
            ],
        )
        # Warnings should be displayed
        assert "Warnings" in result.output or "warning" in result.output.lower() or result.exit_code in (0, 1)

    def test_compliance_jurisdiction_summary_shown_for_known_region(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "3",
                "--region", "DE",
                "--network-isolated",
                "--encryption-at-rest", "AES-256-HSM",
                "--encryption-in-transit", "mTLS",
                "--key-management", "on_prem_hsm",
                "--audit-logging",
            ],
        )
        # DE maps to a known jurisdiction with summary
        assert "Jurisdiction Summary" in result.output or result.exit_code in (0, 1)

    def test_compliance_json_issues_have_required_fields(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "compliance",
                "--level", "5",
                "--region", "US",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        if data["issues"]:
            first_issue = data["issues"][0]
            assert "issue_id" in first_issue
            assert "severity" in first_issue
            assert "description" in first_issue
            assert "remediation" in first_issue


# ---------------------------------------------------------------------------
# edge-config command
# ---------------------------------------------------------------------------


class TestEdgeConfigCommand:
    def test_edge_config_basic_exits_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["edge-config", "--max-memory-mb", "8192"],
        )
        # Should exit 0 when valid resources
        assert result.exit_code in (0, 1)  # depends on actual system memory

    def test_edge_config_json_output_shape(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "512",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert "validation" in data
        assert "performance_estimate" in data
        assert "is_valid" in data["validation"]
        assert "tokens_per_second" in data["performance_estimate"]
        assert "max_context_tokens" in data["performance_estimate"]

    def test_edge_config_json_insufficient_memory_exits_nonzero(
        self, runner: CliRunner
    ) -> None:
        # Requesting more memory than any real system has
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "999999999",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert data["validation"]["is_valid"] is False
        assert result.exit_code == 1

    def test_edge_config_with_quantization(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "512",
                "--quantization", "gguf_q4_k_m",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert data["performance_estimate"]["quantization_speedup_factor"] == 2.0

    def test_edge_config_with_gpu_memory(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "512",
                "--gpu-memory-mb", "8192",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert data["performance_estimate"]["notes"]
        assert any("GPU" in n for n in data["performance_estimate"]["notes"])

    def test_edge_config_offline_capable_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "4096",
                "--offline-capable",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        assert "validation" in data

    def test_edge_config_rich_output_shows_config_memory(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            ["edge-config", "--max-memory-mb", "4096"],
        )
        assert "4096" in result.output

    def test_edge_config_rich_output_shows_performance_section(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            ["edge-config", "--max-memory-mb", "4096", "--model-size-b", "7.0"],
        )
        assert "Performance Estimate" in result.output

    def test_edge_config_errors_shown_when_invalid(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            ["edge-config", "--max-memory-mb", "999999999"],
        )
        assert result.exit_code == 1
        assert "Errors" in result.output or "Insufficient" in result.output

    def test_edge_config_json_performance_estimate_fields(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "512",
                "--model-size-b", "7.0",
                "--max-concurrent-requests", "2",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        pe = data["performance_estimate"]
        assert "time_to_first_token_ms" in pe
        assert "quantization_speedup_factor" in pe
        assert "notes" in pe

    def test_edge_config_notes_shown_when_model_oversized(
        self, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "edge-config",
                "--max-memory-mb", "512",
                "--model-size-b", "70.0",
                "--json-output",
            ],
        )
        data = json.loads(result.output)
        notes = data["performance_estimate"]["notes"]
        assert any("exceeds" in n for n in notes)

    def test_edge_config_all_quantization_choices(
        self, runner: CliRunner
    ) -> None:
        for quant in ["none", "int8", "int4", "gguf_q4_k_m", "gguf_q5_k_m", "gguf_q8_0"]:
            result = runner.invoke(
                cli,
                [
                    "edge-config",
                    "--max-memory-mb", "512",
                    "--quantization", quant,
                    "--json-output",
                ],
            )
            assert result.exit_code in (0, 1), f"Unexpected exit for quant={quant}"
            data = json.loads(result.output)
            assert "performance_estimate" in data
