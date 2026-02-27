"""Tests for the agent_sovereign.bundler package — Phase 7A.

Covers:
- BundleComponent construction and validation
- BundleSovereigntyLevel enum
- BundleManifest CRUD, computed fields, serialisation, checksum verification
- DockerConfig construction
- DockerGenerator Dockerfile, compose, and .dockerignore output
- AgentPackager scanning, packaging, validation
- AttestationGenerator build provenance and integrity attestations
- AttestationGenerator verify, export, import
- CLI bundle sub-commands: package, docker, verify, attest
- Edge cases: empty directories, missing files, invalid checksums
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

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
from agent_sovereign.cli.main import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _make_component(
    name: str = "my-model",
    component_type: str = "model",
    path: str = "models/my-model.gguf",
    size_bytes: int = 1024,
    checksum: str | None = None,
) -> BundleComponent:
    if checksum is None:
        checksum = _sha256(b"placeholder")
    return BundleComponent(
        name=name,
        component_type=component_type,
        path=path,
        size_bytes=size_bytes,
        checksum=checksum,
    )


def _make_manifest(
    sovereignty_level: BundleSovereigntyLevel = BundleSovereigntyLevel.PARTIAL,
    target_platform: str = "docker",
    components: list[BundleComponent] | None = None,
) -> BundleManifest:
    manifest = BundleManifest(
        sovereignty_level=sovereignty_level,
        target_platform=target_platform,
    )
    for comp in components or []:
        manifest.add_component(comp)
    return manifest


def _write_files(
    directory: Path, files: dict[str, bytes]
) -> None:
    """Write {relative_path: content} to *directory*."""
    for rel_path, content in files.items():
        file_path = directory / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)


# ---------------------------------------------------------------------------
# BundleComponent tests
# ---------------------------------------------------------------------------


class TestBundleComponent:
    def test_construction_with_all_fields(self) -> None:
        comp = _make_component()
        assert comp.name == "my-model"
        assert comp.component_type == "model"
        assert comp.path == "models/my-model.gguf"
        assert comp.size_bytes == 1024

    def test_all_valid_component_types(self) -> None:
        for comp_type in ("model", "agent_code", "config", "policy", "data"):
            comp = _make_component(component_type=comp_type)
            assert comp.component_type == comp_type

    def test_invalid_component_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component_type"):
            _make_component(component_type="firmware")

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            _make_component(name="")

    def test_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            _make_component(path="")

    def test_empty_checksum_raises(self) -> None:
        with pytest.raises(ValueError, match="checksum must not be empty"):
            BundleComponent(
                name="x",
                component_type="config",
                path="x.yaml",
                size_bytes=10,
                checksum="",
            )

    def test_negative_size_bytes_raises(self) -> None:
        with pytest.raises(ValueError, match="size_bytes must be >= 0"):
            _make_component(size_bytes=-1)

    def test_zero_size_bytes_is_valid(self) -> None:
        comp = _make_component(size_bytes=0)
        assert comp.size_bytes == 0

    def test_frozen_dataclass_immutable(self) -> None:
        comp = _make_component()
        with pytest.raises((AttributeError, TypeError)):
            comp.name = "other"  # type: ignore[misc]

    def test_equality_same_values(self) -> None:
        checksum = _sha256(b"data")
        comp1 = BundleComponent("n", "config", "p.yaml", 10, checksum)
        comp2 = BundleComponent("n", "config", "p.yaml", 10, checksum)
        assert comp1 == comp2

    def test_equality_different_checksum(self) -> None:
        comp1 = BundleComponent("n", "config", "p.yaml", 10, _sha256(b"a"))
        comp2 = BundleComponent("n", "config", "p.yaml", 10, _sha256(b"b"))
        assert comp1 != comp2

    def test_checksum_field_stored(self) -> None:
        checksum = _sha256(b"my content")
        comp = _make_component(checksum=checksum)
        assert comp.checksum == checksum


# ---------------------------------------------------------------------------
# BundleSovereigntyLevel tests
# ---------------------------------------------------------------------------


class TestBundleSovereigntyLevel:
    def test_full_value(self) -> None:
        assert BundleSovereigntyLevel.FULL.value == "full"

    def test_partial_value(self) -> None:
        assert BundleSovereigntyLevel.PARTIAL.value == "partial"

    def test_minimal_value(self) -> None:
        assert BundleSovereigntyLevel.MINIMAL.value == "minimal"

    def test_from_string(self) -> None:
        assert BundleSovereigntyLevel("full") == BundleSovereigntyLevel.FULL

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            BundleSovereigntyLevel("ultra")

    def test_all_levels_are_strings(self) -> None:
        for level in BundleSovereigntyLevel:
            assert isinstance(level.value, str)

    def test_three_levels_exist(self) -> None:
        assert len(list(BundleSovereigntyLevel)) == 3


# ---------------------------------------------------------------------------
# BundleManifest tests
# ---------------------------------------------------------------------------


class TestBundleManifest:
    def test_default_bundle_id_is_uuid_format(self) -> None:
        manifest = _make_manifest()
        # UUID4 pattern: 8-4-4-4-12 hex chars
        import re
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(manifest.bundle_id)

    def test_default_created_at_is_utc(self) -> None:
        manifest = _make_manifest()
        assert manifest.created_at.tzinfo is not None

    def test_custom_bundle_id(self) -> None:
        manifest = BundleManifest(
            bundle_id="custom-id-123",
            sovereignty_level=BundleSovereigntyLevel.FULL,
            target_platform="edge",
        )
        assert manifest.bundle_id == "custom-id-123"

    def test_sovereignty_level_stored(self) -> None:
        manifest = _make_manifest(BundleSovereigntyLevel.FULL)
        assert manifest.sovereignty_level == BundleSovereigntyLevel.FULL

    def test_target_platform_stored(self) -> None:
        manifest = _make_manifest(target_platform="kubernetes")
        assert manifest.target_platform == "kubernetes"

    def test_empty_components_default(self) -> None:
        manifest = _make_manifest()
        assert manifest.components == []

    def test_empty_metadata_default(self) -> None:
        manifest = _make_manifest()
        assert manifest.metadata == {}

    def test_compute_total_size_empty(self) -> None:
        manifest = _make_manifest()
        assert manifest.compute_total_size() == 0

    def test_compute_total_size_with_components(self) -> None:
        comp1 = _make_component(name="a", size_bytes=100)
        comp2 = _make_component(name="b", component_type="config", path="b.yaml", size_bytes=200)
        manifest = _make_manifest(components=[comp1, comp2])
        assert manifest.compute_total_size() == 300

    def test_total_size_bytes_computed_field(self) -> None:
        comp = _make_component(size_bytes=512)
        manifest = _make_manifest(components=[comp])
        assert manifest.total_size_bytes == 512

    def test_add_component(self) -> None:
        manifest = _make_manifest()
        comp = _make_component()
        manifest.add_component(comp)
        assert len(manifest.components) == 1
        assert manifest.components[0] == comp

    def test_add_duplicate_component_raises(self) -> None:
        manifest = _make_manifest()
        comp = _make_component()
        manifest.add_component(comp)
        with pytest.raises(ValueError, match="already exists"):
            manifest.add_component(comp)

    def test_remove_component(self) -> None:
        comp = _make_component(name="removable")
        manifest = _make_manifest(components=[comp])
        manifest.remove_component("removable")
        assert len(manifest.components) == 0

    def test_remove_nonexistent_component_raises(self) -> None:
        manifest = _make_manifest()
        with pytest.raises(KeyError):
            manifest.remove_component("ghost")

    def test_add_multiple_components(self) -> None:
        manifest = _make_manifest()
        for index in range(5):
            comp = _make_component(
                name=f"comp-{index}",
                component_type="config",
                path=f"config-{index}.yaml",
            )
            manifest.add_component(comp)
        assert len(manifest.components) == 5

    def test_to_json_returns_string(self) -> None:
        manifest = _make_manifest()
        result = manifest.to_json()
        assert isinstance(result, str)

    def test_to_json_is_valid_json(self) -> None:
        manifest = _make_manifest()
        raw = manifest.to_json()
        parsed = json.loads(raw)
        assert "bundle_id" in parsed
        assert "sovereignty_level" in parsed

    def test_to_json_includes_components(self) -> None:
        comp = _make_component()
        manifest = _make_manifest(components=[comp])
        raw = json.loads(manifest.to_json())
        assert len(raw["components"]) == 1
        assert raw["components"][0]["name"] == "my-model"

    def test_from_json_roundtrip(self) -> None:
        comp = _make_component()
        original = _make_manifest(
            sovereignty_level=BundleSovereigntyLevel.FULL,
            target_platform="edge",
            components=[comp],
        )
        json_str = original.to_json()
        restored = BundleManifest.from_json(json_str)
        assert restored.bundle_id == original.bundle_id
        assert restored.sovereignty_level == BundleSovereigntyLevel.FULL
        assert restored.target_platform == "edge"
        assert len(restored.components) == 1
        assert restored.components[0].name == comp.name

    def test_from_json_preserves_checksum(self) -> None:
        checksum = _sha256(b"real content")
        comp = _make_component(checksum=checksum)
        manifest = _make_manifest(components=[comp])
        restored = BundleManifest.from_json(manifest.to_json())
        assert restored.components[0].checksum == checksum

    def test_from_json_preserves_metadata(self) -> None:
        manifest = BundleManifest(
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
            target_platform="docker",
            metadata={"env": "production", "version": "1.2.3"},
        )
        restored = BundleManifest.from_json(manifest.to_json())
        assert restored.metadata["env"] == "production"
        assert restored.metadata["version"] == "1.2.3"

    def test_verify_checksums_all_valid(self, tmp_path: Path) -> None:
        content = b"model weights"
        checksum = _sha256(content)
        file_path = tmp_path / "model.bin"
        file_path.write_bytes(content)

        comp = BundleComponent(
            name="model",
            component_type="model",
            path="model.bin",
            size_bytes=len(content),
            checksum=checksum,
        )
        manifest = _make_manifest(components=[comp])
        results = manifest.verify_checksums(tmp_path)

        assert len(results) == 1
        assert results[0] == ("model", True)

    def test_verify_checksums_invalid_checksum(self, tmp_path: Path) -> None:
        content = b"real content"
        file_path = tmp_path / "model.bin"
        file_path.write_bytes(content)

        comp = BundleComponent(
            name="model",
            component_type="model",
            path="model.bin",
            size_bytes=len(content),
            checksum="a" * 64,  # wrong checksum
        )
        manifest = _make_manifest(components=[comp])
        results = manifest.verify_checksums(tmp_path)

        assert results[0] == ("model", False)

    def test_verify_checksums_missing_file(self, tmp_path: Path) -> None:
        comp = BundleComponent(
            name="ghost",
            component_type="data",
            path="ghost.bin",
            size_bytes=0,
            checksum="a" * 64,
        )
        manifest = _make_manifest(components=[comp])
        results = manifest.verify_checksums(tmp_path)

        assert results[0] == ("ghost", False)

    def test_verify_checksums_empty_components(self, tmp_path: Path) -> None:
        manifest = _make_manifest()
        results = manifest.verify_checksums(tmp_path)
        assert results == []

    def test_verify_checksums_mixed_results(self, tmp_path: Path) -> None:
        good_content = b"good"
        good_checksum = _sha256(good_content)
        (tmp_path / "good.bin").write_bytes(good_content)

        bad_content = b"bad"
        bad_checksum = "b" * 64  # wrong
        (tmp_path / "bad.bin").write_bytes(bad_content)

        comp_good = BundleComponent("good", "data", "good.bin", 4, good_checksum)
        comp_bad = BundleComponent("bad", "data", "bad.bin", 3, bad_checksum)
        manifest = _make_manifest(components=[comp_good, comp_bad])

        results = dict(manifest.verify_checksums(tmp_path))
        assert results["good"] is True
        assert results["bad"] is False


# ---------------------------------------------------------------------------
# DockerConfig tests
# ---------------------------------------------------------------------------


class TestDockerConfig:
    def test_default_base_image(self) -> None:
        config = DockerConfig()
        assert config.base_image == "python:3.11-slim"

    def test_default_python_version(self) -> None:
        config = DockerConfig()
        assert config.python_version == "3.11"

    def test_default_expose_ports(self) -> None:
        config = DockerConfig()
        assert config.expose_ports == [8080]

    def test_custom_base_image(self) -> None:
        config = DockerConfig(base_image="debian:bookworm-slim")
        assert config.base_image == "debian:bookworm-slim"

    def test_custom_ports(self) -> None:
        config = DockerConfig(expose_ports=[8080, 9090])
        assert 9090 in config.expose_ports

    def test_env_vars_stored(self) -> None:
        config = DockerConfig(env_vars={"PYTHONPATH": "/app"})
        assert config.env_vars["PYTHONPATH"] == "/app"

    def test_healthcheck_cmd_stored(self) -> None:
        cmd = "curl -f http://localhost:8080/health"
        config = DockerConfig(healthcheck_cmd=cmd)
        assert config.healthcheck_cmd == cmd

    def test_healthcheck_cmd_default_none(self) -> None:
        config = DockerConfig()
        assert config.healthcheck_cmd is None

    def test_labels_stored(self) -> None:
        config = DockerConfig(labels={"org.opencontainers.image.title": "test"})
        assert config.labels["org.opencontainers.image.title"] == "test"

    def test_frozen_immutability(self) -> None:
        config = DockerConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.base_image = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DockerGenerator tests
# ---------------------------------------------------------------------------


class TestDockerGenerator:
    @pytest.fixture()
    def generator(self) -> DockerGenerator:
        return DockerGenerator()

    @pytest.fixture()
    def manifest(self) -> BundleManifest:
        comp = _make_component(
            name="agent-code",
            component_type="agent_code",
            path="src/agent.py",
        )
        return _make_manifest(components=[comp])

    @pytest.fixture()
    def config(self) -> DockerConfig:
        return DockerConfig(
            healthcheck_cmd="curl -f http://localhost:8080/health",
            env_vars={"LOG_LEVEL": "info"},
        )

    def test_generate_dockerfile_returns_string(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert isinstance(result, str)

    def test_dockerfile_starts_with_syntax_comment(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "# syntax=docker/dockerfile:1" in result

    def test_dockerfile_has_builder_stage(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "AS builder" in result

    def test_dockerfile_has_runtime_stage(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "AS runtime" in result

    def test_dockerfile_uses_non_root_user(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "agentuser" in result
        assert "USER agentuser" in result

    def test_dockerfile_exposes_port(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "EXPOSE 8080" in result

    def test_dockerfile_has_healthcheck_when_configured(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "HEALTHCHECK" in result
        assert "curl -f" in result

    def test_dockerfile_no_healthcheck_when_none(
        self, generator: DockerGenerator, manifest: BundleManifest
    ) -> None:
        config = DockerConfig()
        result = generator.generate_dockerfile(manifest, config)
        assert "HEALTHCHECK" not in result

    def test_dockerfile_includes_env_vars(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "LOG_LEVEL" in result

    def test_dockerfile_includes_bundle_id_comment(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert manifest.bundle_id in result

    def test_dockerfile_full_sovereignty_includes_mode_env(
        self, generator: DockerGenerator, config: DockerConfig
    ) -> None:
        full_manifest = _make_manifest(
            sovereignty_level=BundleSovereigntyLevel.FULL
        )
        result = generator.generate_dockerfile(full_manifest, config)
        assert "AGENT_SOVEREIGN_MODE=full" in result

    def test_dockerfile_copies_requirements(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "requirements.txt" in result

    def test_dockerfile_includes_label_with_sovereignty(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "com.aumos.sovereignty" in result

    def test_dockerfile_has_entrypoint(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_dockerfile(manifest, config)
        assert "ENTRYPOINT" in result

    def test_generate_compose_returns_string(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config, "my-agent")
        assert isinstance(result, str)

    def test_generate_compose_has_version(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert "version:" in result

    def test_generate_compose_includes_service_name(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config, "my-agent")
        assert "my-agent:" in result

    def test_generate_compose_default_service_name(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert "agent:" in result

    def test_generate_compose_full_sovereignty_uses_network_none(
        self, generator: DockerGenerator, config: DockerConfig
    ) -> None:
        full_manifest = _make_manifest(sovereignty_level=BundleSovereigntyLevel.FULL)
        result = generator.generate_compose(full_manifest, config)
        assert "network_mode: none" in result

    def test_generate_compose_partial_sovereignty_has_bridge_network(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert "agent-net:" in result

    def test_generate_compose_ports_included(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert "8080:8080" in result

    def test_generate_compose_bundle_id_in_comment(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert manifest.bundle_id in result

    def test_generate_compose_healthcheck_included(
        self, generator: DockerGenerator, manifest: BundleManifest, config: DockerConfig
    ) -> None:
        result = generator.generate_compose(manifest, config)
        assert "healthcheck:" in result

    def test_generate_compose_model_volumes_added(
        self, generator: DockerGenerator, config: DockerConfig
    ) -> None:
        model_comp = _make_component(
            name="llama-3",
            component_type="model",
            path="models/llama-3.gguf",
        )
        manifest = _make_manifest(components=[model_comp])
        result = generator.generate_compose(manifest, config)
        assert "volumes:" in result
        assert "models" in result

    def test_generate_dockerignore_returns_string(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert isinstance(result, str)

    def test_dockerignore_excludes_git(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert ".git" in result

    def test_dockerignore_excludes_pycache(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert "__pycache__" in result

    def test_dockerignore_excludes_venv(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert ".venv" in result

    def test_dockerignore_excludes_tests(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert "tests/" in result

    def test_dockerignore_excludes_env_files(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert ".env" in result

    def test_dockerignore_excludes_dotfiles(
        self, generator: DockerGenerator
    ) -> None:
        result = generator.generate_dockerignore()
        assert ".DS_Store" in result

    def test_generate_dockerfile_custom_base_image(
        self, generator: DockerGenerator, manifest: BundleManifest
    ) -> None:
        config = DockerConfig(base_image="debian:bookworm-slim")
        result = generator.generate_dockerfile(manifest, config)
        assert "debian:bookworm-slim" in result

    def test_generate_dockerfile_multiple_ports(
        self, generator: DockerGenerator, manifest: BundleManifest
    ) -> None:
        config = DockerConfig(expose_ports=[8080, 9090, 3000])
        result = generator.generate_dockerfile(manifest, config)
        assert "EXPOSE 8080" in result
        assert "EXPOSE 9090" in result
        assert "EXPOSE 3000" in result


# ---------------------------------------------------------------------------
# AgentPackager tests
# ---------------------------------------------------------------------------


class TestAgentPackager:
    @pytest.fixture()
    def output_dir(self, tmp_path: Path) -> Path:
        out = tmp_path / "output"
        out.mkdir()
        return out

    @pytest.fixture()
    def config(self, output_dir: Path) -> PackageConfig:
        return PackageConfig(output_dir=output_dir)

    @pytest.fixture()
    def packager(self, config: PackageConfig) -> AgentPackager:
        return AgentPackager(config)

    def test_package_nonexistent_dir_raises(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            packager.package(
                source_dir=tmp_path / "does_not_exist",
                sovereignty_level=BundleSovereigntyLevel.PARTIAL,
            )

    def test_package_file_instead_of_dir_raises(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        a_file = tmp_path / "file.txt"
        a_file.write_text("hello")
        with pytest.raises(ValueError, match="must be a directory"):
            packager.package(
                source_dir=a_file,
                sovereignty_level=BundleSovereigntyLevel.PARTIAL,
            )

    def test_package_empty_directory_returns_manifest(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "empty_src"
        source.mkdir()
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        assert isinstance(manifest, BundleManifest)
        assert manifest.components == []

    def test_package_scans_files(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("print('hello')")
        (source / "config.yaml").write_text("key: value")

        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        assert len(manifest.components) == 2

    def test_package_classifies_python_as_agent_code(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        assert manifest.components[0].component_type == "agent_code"

    def test_package_classifies_yaml_as_config(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "settings.yaml").write_text("debug: true")
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        assert manifest.components[0].component_type == "config"

    def test_package_classifies_gguf_as_model(
        self, tmp_path: Path, output_dir: Path
    ) -> None:
        config = PackageConfig(output_dir=output_dir, include_model=True)
        packager = AgentPackager(config)
        source = tmp_path / "src"
        source.mkdir()
        (source / "model.gguf").write_bytes(b"\x00" * 100)
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.FULL,
        )
        assert manifest.components[0].component_type == "model"

    def test_package_excludes_model_when_flag_false(
        self, tmp_path: Path, output_dir: Path
    ) -> None:
        config = PackageConfig(output_dir=output_dir, include_model=False)
        packager = AgentPackager(config)
        source = tmp_path / "src"
        source.mkdir()
        (source / "model.gguf").write_bytes(b"\x00" * 100)
        (source / "agent.py").write_text("x = 1")
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        types = [c.component_type for c in manifest.components]
        assert "model" not in types

    def test_package_excludes_test_files_by_default(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        (source / "test_agent.py").write_text("def test_x(): pass")
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        names = [c.name for c in manifest.components]
        assert not any("test_" in n for n in names)

    def test_package_includes_test_files_when_flag_set(
        self, tmp_path: Path, output_dir: Path
    ) -> None:
        config = PackageConfig(output_dir=output_dir, include_tests=True)
        packager = AgentPackager(config)
        source = tmp_path / "src"
        source.mkdir()
        (source / "test_agent.py").write_text("def test_x(): pass")
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
        )
        assert len(manifest.components) == 1

    def test_package_sovereignty_level_stored(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.FULL,
        )
        assert manifest.sovereignty_level == BundleSovereigntyLevel.FULL

    def test_package_target_platform_stored(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        manifest = packager.package(
            source_dir=source,
            sovereignty_level=BundleSovereigntyLevel.MINIMAL,
            target_platform="kubernetes",
        )
        assert manifest.target_platform == "kubernetes"

    def test_compute_checksum_correct(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        content = b"hello world"
        file_path = tmp_path / "file.bin"
        file_path.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert packager.compute_checksum(file_path) == expected

    def test_compute_checksum_missing_file_raises(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            packager.compute_checksum(tmp_path / "missing.bin")

    def test_compute_checksum_returns_64_chars(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "f.bin"
        file_path.write_bytes(b"data")
        checksum = packager.compute_checksum(file_path)
        assert len(checksum) == 64

    def test_estimate_bundle_size_empty(
        self, packager: AgentPackager
    ) -> None:
        assert packager.estimate_bundle_size([]) == 0

    def test_estimate_bundle_size_sum(
        self, packager: AgentPackager
    ) -> None:
        comps = [
            _make_component(name="a", size_bytes=100),
            _make_component(name="b", component_type="config", path="b.yaml", size_bytes=200),
        ]
        assert packager.estimate_bundle_size(comps) == 300

    def test_validate_bundle_no_components(
        self, packager: AgentPackager, output_dir: Path
    ) -> None:
        manifest = _make_manifest()
        errors = packager.validate_bundle(manifest, output_dir)
        assert any("no components" in e.lower() for e in errors)

    def test_validate_bundle_valid_manifest(
        self, packager: AgentPackager, output_dir: Path
    ) -> None:
        comp = _make_component()
        manifest = _make_manifest(components=[comp])
        errors = packager.validate_bundle(manifest, output_dir)
        assert errors == []

    def test_validate_bundle_invalid_checksum(
        self, packager: AgentPackager, output_dir: Path
    ) -> None:
        bad_comp = BundleComponent(
            name="bad",
            component_type="data",
            path="bad.bin",
            size_bytes=10,
            checksum="not-a-valid-sha256",
        )
        manifest = _make_manifest(components=[bad_comp])
        errors = packager.validate_bundle(manifest, output_dir)
        assert any("invalid checksum" in e.lower() for e in errors)

    def test_validate_bundle_duplicate_paths(
        self, packager: AgentPackager, output_dir: Path
    ) -> None:
        comp1 = BundleComponent("a", "config", "shared.yaml", 10, _sha256(b"a"))
        comp2 = BundleComponent("b", "config", "shared.yaml", 10, _sha256(b"b"))
        manifest = BundleManifest(
            sovereignty_level=BundleSovereigntyLevel.PARTIAL,
            target_platform="docker",
            components=[comp1, comp2],
        )
        errors = packager.validate_bundle(manifest, output_dir)
        assert any("duplicate" in e.lower() for e in errors)

    def test_validate_bundle_output_dir_is_file(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        file_as_dir = tmp_path / "not_a_dir.txt"
        file_as_dir.write_text("oops")
        comp = _make_component()
        manifest = _make_manifest(components=[comp])
        errors = packager.validate_bundle(manifest, file_as_dir)
        assert any("not a directory" in e.lower() for e in errors)

    def test_scan_directory_excludes_pycache(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "cached.pyc").write_bytes(b"cache")
        (source / "agent.py").write_text("x = 1")
        components = packager.scan_directory(source)
        paths = [c.path for c in components]
        assert not any("__pycache__" in p for p in paths)

    def test_scan_directory_empty(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "empty"
        source.mkdir()
        components = packager.scan_directory(source)
        assert components == []

    def test_scan_directory_nested_files(
        self, packager: AgentPackager, tmp_path: Path
    ) -> None:
        source = tmp_path / "nested"
        source.mkdir()
        (source / "sub").mkdir()
        (source / "sub" / "agent.py").write_text("x = 1")
        components = packager.scan_directory(source)
        assert len(components) == 1
        assert "sub/agent.py" in components[0].path


# ---------------------------------------------------------------------------
# AttestationGenerator tests
# ---------------------------------------------------------------------------


class TestAttestationGenerator:
    @pytest.fixture()
    def generator(self) -> AttestationGenerator:
        return AttestationGenerator(issuer="test-issuer")

    @pytest.fixture()
    def manifest(self) -> BundleManifest:
        comp = _make_component()
        return _make_manifest(
            sovereignty_level=BundleSovereigntyLevel.FULL,
            components=[comp],
        )

    def test_build_provenance_returns_attestation(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert isinstance(att, Attestation)

    def test_build_provenance_type(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert att.attestation_type == AttestationType.BUILD_PROVENANCE

    def test_build_provenance_subject_is_bundle_id(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert att.subject == manifest.bundle_id

    def test_build_provenance_issuer(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert att.issuer == "test-issuer"

    def test_build_provenance_has_signature(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert att.signature is not None
        assert len(att.signature) == 64

    def test_build_provenance_claims_contain_component_hashes(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert "component_hashes" in att.claims
        assert "my-model" in att.claims["component_hashes"]

    def test_build_provenance_claims_contain_platform(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert "platform" in att.claims
        assert "python_version" in att.claims

    def test_build_provenance_unique_ids(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att1 = generator.generate_build_provenance(manifest)
        att2 = generator.generate_build_provenance(manifest)
        assert att1.attestation_id != att2.attestation_id

    def test_build_provenance_issued_at_is_utc(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert att.issued_at.tzinfo is not None

    def test_integrity_attestation_returns_attestation(
        self, generator: AttestationGenerator, manifest: BundleManifest, tmp_path: Path
    ) -> None:
        content = b"model weights"
        checksum = _sha256(content)
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "my-model.gguf").write_bytes(content)

        comp = BundleComponent(
            name="my-model",
            component_type="model",
            path="models/my-model.gguf",
            size_bytes=len(content),
            checksum=checksum,
        )
        manifest2 = _make_manifest(components=[comp])
        att = generator.generate_integrity_attestation(manifest2, tmp_path)
        assert att.attestation_type == AttestationType.INTEGRITY_VERIFICATION

    def test_integrity_attestation_all_valid(
        self, generator: AttestationGenerator, tmp_path: Path
    ) -> None:
        content = b"config content"
        checksum = _sha256(content)
        (tmp_path / "config.yaml").write_bytes(content)

        comp = BundleComponent("cfg", "config", "config.yaml", len(content), checksum)
        manifest = _make_manifest(components=[comp])

        att = generator.generate_integrity_attestation(manifest, tmp_path)
        assert att.claims["all_checksums_valid"] is True
        assert att.claims["passed_count"] == 1
        assert att.claims["failed_count"] == 0

    def test_integrity_attestation_missing_file(
        self, generator: AttestationGenerator, tmp_path: Path
    ) -> None:
        comp = BundleComponent("ghost", "data", "ghost.bin", 0, "a" * 64)
        manifest = _make_manifest(components=[comp])

        att = generator.generate_integrity_attestation(manifest, tmp_path)
        assert att.claims["all_checksums_valid"] is False
        assert att.claims["failed_count"] == 1

    def test_verify_attestation_valid(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        assert generator.verify_attestation(att) is True

    def test_verify_attestation_tampered_claims(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        # Tamper with claims — signature will no longer match
        tampered_claims = dict(att.claims)
        tampered_claims["component_count"] = 999
        tampered_att = Attestation(
            attestation_id=att.attestation_id,
            attestation_type=att.attestation_type,
            subject=att.subject,
            issuer=att.issuer,
            issued_at=att.issued_at,
            claims=tampered_claims,
            signature=att.signature,
        )
        assert generator.verify_attestation(tampered_att) is False

    def test_verify_attestation_none_signature(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = Attestation(
            attestation_id="test",
            attestation_type=AttestationType.BUILD_PROVENANCE,
            subject=manifest.bundle_id,
            issuer="test",
            issued_at=datetime.datetime.now(datetime.timezone.utc),
            claims={},
            signature=None,
        )
        assert generator.verify_attestation(att) is False

    def test_verify_attestation_wrong_signature(
        self, generator: AttestationGenerator, manifest: BundleManifest
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        bad_att = Attestation(
            attestation_id=att.attestation_id,
            attestation_type=att.attestation_type,
            subject=att.subject,
            issuer=att.issuer,
            issued_at=att.issued_at,
            claims=att.claims,
            signature="0" * 64,
        )
        assert generator.verify_attestation(bad_att) is False

    def test_export_and_import_attestations(
        self, generator: AttestationGenerator, manifest: BundleManifest, tmp_path: Path
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        export_path = tmp_path / "attestations.json"
        generator.export_attestations([att], export_path)

        imported = generator.import_attestations(export_path)
        assert len(imported) == 1
        assert imported[0].attestation_id == att.attestation_id
        assert imported[0].attestation_type == AttestationType.BUILD_PROVENANCE

    def test_export_attestations_creates_valid_json(
        self, generator: AttestationGenerator, manifest: BundleManifest, tmp_path: Path
    ) -> None:
        att = generator.generate_build_provenance(manifest)
        export_path = tmp_path / "att.json"
        generator.export_attestations([att], export_path)

        raw = json.loads(export_path.read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        assert raw[0]["attestation_id"] == att.attestation_id

    def test_import_attestations_file_not_found(
        self, generator: AttestationGenerator, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            generator.import_attestations(tmp_path / "missing.json")

    def test_export_multiple_attestations(
        self, generator: AttestationGenerator, manifest: BundleManifest, tmp_path: Path
    ) -> None:
        att1 = generator.generate_build_provenance(manifest)
        att2 = generator.generate_build_provenance(manifest)
        export_path = tmp_path / "multi.json"
        generator.export_attestations([att1, att2], export_path)

        imported = generator.import_attestations(export_path)
        assert len(imported) == 2

    def test_verify_integrity_attestation(
        self, generator: AttestationGenerator, tmp_path: Path
    ) -> None:
        content = b"data"
        checksum = _sha256(content)
        (tmp_path / "data.bin").write_bytes(content)
        comp = BundleComponent("d", "data", "data.bin", len(content), checksum)
        manifest = _make_manifest(components=[comp])
        att = generator.generate_integrity_attestation(manifest, tmp_path)
        assert generator.verify_attestation(att) is True

    def test_attestation_type_values(self) -> None:
        assert AttestationType.BUILD_PROVENANCE.value == "build_provenance"
        assert AttestationType.SECURITY_SCAN.value == "security_scan"
        assert AttestationType.COMPLIANCE_CHECK.value == "compliance_check"
        assert AttestationType.INTEGRITY_VERIFICATION.value == "integrity_verification"


# ---------------------------------------------------------------------------
# CLI bundle command tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestBundlePackageCLI:
    def test_package_basic(self, runner: CliRunner, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--sovereignty", "partial",
            ],
        )
        assert result.exit_code == 0
        assert (output / "manifest.json").exists()

    def test_package_json_output(self, runner: CliRunner, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "config.yaml").write_text("debug: true")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "bundle_id" in data
        assert "component_count" in data
        assert "total_size_bytes" in data
        assert "manifest_path" in data

    def test_package_sovereignty_full(self, runner: CliRunner, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--sovereignty", "full",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sovereignty_level"] == "full"

    def test_package_nonexistent_source_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(tmp_path / "nope"),
                "--output", str(tmp_path / "out"),
            ],
        )
        # Click's path validation catches this before the command body
        assert result.exit_code != 0

    def test_package_with_target_platform(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--platform", "kubernetes",
                "--json-output",
            ],
        )
        assert result.exit_code == 0

    def test_package_compress_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--compress",
            ],
        )
        assert result.exit_code == 0

    def test_package_rich_output_shows_bundle_info(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "agent.py").write_text("x = 1")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
            ],
        )
        assert result.exit_code == 0
        assert "Bundle Manifest Created" in result.output

    def test_package_minimal_sovereignty(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "src"
        source.mkdir()
        (source / "config.yaml").write_text("endpoint: https://api.example.com")
        output = tmp_path / "dist"

        result = runner.invoke(
            cli,
            [
                "bundle", "package",
                "--source", str(source),
                "--output", str(output),
                "--sovereignty", "minimal",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sovereignty_level"] == "minimal"


class TestBundleDockerCLI:
    @pytest.fixture()
    def manifest_file(self, tmp_path: Path) -> Path:
        comp = _make_component(
            name="agent",
            component_type="agent_code",
            path="src/agent.py",
        )
        manifest = _make_manifest(components=[comp])
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        return manifest_path

    def test_docker_generates_files(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "docker_out"
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(manifest_file),
                "--output", str(output),
            ],
        )
        assert result.exit_code == 0
        assert (output / "Dockerfile").exists()
        assert (output / "docker-compose.yml").exists()
        assert (output / ".dockerignore").exists()

    def test_docker_json_output(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "docker_out"
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(manifest_file),
                "--output", str(output),
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "dockerfile" in data
        assert "compose" in data

    def test_docker_custom_base_image(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "docker_out"
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(manifest_file),
                "--output", str(output),
                "--base-image", "debian:bookworm-slim",
            ],
        )
        assert result.exit_code == 0
        dockerfile_content = (output / "Dockerfile").read_text()
        assert "debian:bookworm-slim" in dockerfile_content

    def test_docker_custom_service_name(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "docker_out"
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(manifest_file),
                "--output", str(output),
                "--service-name", "my-sovereign-agent",
            ],
        )
        assert result.exit_code == 0
        compose_content = (output / "docker-compose.yml").read_text()
        assert "my-sovereign-agent:" in compose_content

    def test_docker_invalid_manifest_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        bad_manifest = tmp_path / "bad.json"
        bad_manifest.write_text("not valid json at all {{{", encoding="utf-8")
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(bad_manifest),
                "--output", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code != 0

    def test_docker_with_healthcheck(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "docker_out"
        result = runner.invoke(
            cli,
            [
                "bundle", "docker",
                "--manifest", str(manifest_file),
                "--output", str(output),
                "--healthcheck", "curl -f http://localhost:8080/health",
            ],
        )
        assert result.exit_code == 0
        dockerfile_content = (output / "Dockerfile").read_text()
        assert "HEALTHCHECK" in dockerfile_content


class TestBundleVerifyCLI:
    @pytest.fixture()
    def bundle_setup(self, tmp_path: Path) -> tuple[Path, Path]:
        """Return (manifest_path, bundle_dir) with a valid file."""
        content = b"agent code"
        checksum = _sha256(content)
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        (bundle_dir / "agent.py").write_bytes(content)

        comp = BundleComponent("agent", "agent_code", "agent.py", len(content), checksum)
        manifest = _make_manifest(components=[comp])
        manifest_path = bundle_dir / "manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        return manifest_path, bundle_dir

    def test_verify_valid_bundle_exits_zero(
        self,
        runner: CliRunner,
        bundle_setup: tuple[Path, Path],
    ) -> None:
        manifest_path, bundle_dir = bundle_setup
        result = runner.invoke(
            cli,
            [
                "bundle", "verify",
                "--manifest", str(manifest_path),
                "--bundle-dir", str(bundle_dir),
            ],
        )
        assert result.exit_code == 0

    def test_verify_json_output_valid(
        self,
        runner: CliRunner,
        bundle_setup: tuple[Path, Path],
    ) -> None:
        manifest_path, bundle_dir = bundle_setup
        result = runner.invoke(
            cli,
            [
                "bundle", "verify",
                "--manifest", str(manifest_path),
                "--bundle-dir", str(bundle_dir),
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["all_valid"] is True
        assert len(data["results"]) == 1

    def test_verify_invalid_bundle_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        # File exists but checksum is wrong
        (bundle_dir / "agent.py").write_bytes(b"different content")

        comp = BundleComponent("agent", "agent_code", "agent.py", 5, "a" * 64)
        manifest = _make_manifest(components=[comp])
        manifest_path = bundle_dir / "manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "bundle", "verify",
                "--manifest", str(manifest_path),
                "--bundle-dir", str(bundle_dir),
                "--json-output",
            ],
        )
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["all_valid"] is False

    def test_verify_rich_output_shows_table(
        self,
        runner: CliRunner,
        bundle_setup: tuple[Path, Path],
    ) -> None:
        manifest_path, bundle_dir = bundle_setup
        result = runner.invoke(
            cli,
            [
                "bundle", "verify",
                "--manifest", str(manifest_path),
                "--bundle-dir", str(bundle_dir),
            ],
        )
        assert "agent" in result.output


class TestBundleAttestCLI:
    @pytest.fixture()
    def manifest_file(self, tmp_path: Path) -> Path:
        comp = _make_component(
            name="agent-code",
            component_type="agent_code",
            path="src/agent.py",
        )
        manifest = _make_manifest(components=[comp])
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        return manifest_path

    def test_attest_creates_output_file(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        result = runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert output_path.exists()

    def test_attest_json_output(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        result = runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "bundle_id" in data
        assert "attestation_count" in data
        assert data["attestation_count"] == 2
        assert "attestations" in data

    def test_attest_output_file_is_valid_json(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
            ],
        )
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        assert len(raw) == 2

    def test_attest_output_has_required_fields(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
            ],
        )
        attestations = json.loads(output_path.read_text(encoding="utf-8"))
        for att in attestations:
            assert "attestation_id" in att
            assert "attestation_type" in att
            assert "subject" in att
            assert "issuer" in att
            assert "issued_at" in att

    def test_attest_custom_issuer(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        result = runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
                "--issuer", "my-ci-pipeline",
                "--json-output",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert all(
            att["issuer"] == "my-ci-pipeline"
            for att in data["attestations"]
        )

    def test_attest_invalid_manifest_fails(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        bad_manifest = tmp_path / "bad.json"
        bad_manifest.write_text("{invalid", encoding="utf-8")
        result = runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(bad_manifest),
                "--output", str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code != 0

    def test_attest_rich_output_mentions_attestation_count(
        self, runner: CliRunner, manifest_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "attestations.json"
        result = runner.invoke(
            cli,
            [
                "bundle", "attest",
                "--manifest", str(manifest_file),
                "--output", str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert "attestation" in result.output.lower()


class TestBundleGroupCLI:
    def test_bundle_group_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["bundle", "--help"])
        assert result.exit_code == 0
        assert "package" in result.output
        assert "docker" in result.output
        assert "verify" in result.output
        assert "attest" in result.output

    def test_bundle_package_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["bundle", "package", "--help"])
        assert result.exit_code == 0
        assert "--source" in result.output
        assert "--output" in result.output
        assert "--sovereignty" in result.output

    def test_bundle_docker_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["bundle", "docker", "--help"])
        assert result.exit_code == 0
        assert "--manifest" in result.output

    def test_bundle_verify_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["bundle", "verify", "--help"])
        assert result.exit_code == 0
        assert "--bundle-dir" in result.output

    def test_bundle_attest_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["bundle", "attest", "--help"])
        assert result.exit_code == 0
        assert "--issuer" in result.output
