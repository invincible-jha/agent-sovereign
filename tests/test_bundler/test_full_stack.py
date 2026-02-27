"""Tests for the full_stack bundler module.

Covers:
- AumOSComponent validation and frozen behaviour
- FullStackBundle frozen behaviour and properties
- FullStackBundler.bundle() basic flow
- Dependency resolution is invoked and transitive deps added
- Environment variables propagation
- Docker compose generation (present/absent)
- requirements.txt embedded in bundle
- export_to_directory writes expected files
- Error cases: empty agent name, empty component name/version
- Optional vs required components
- repr and property helpers
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from agent_sovereign.bundler.dependency_resolver import DependencyResolver
from agent_sovereign.bundler.full_stack import (
    AumOSComponent,
    FullStackBundle,
    FullStackBundler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    name: str = "agentshield",
    version: str = "1.0.0",
    config: dict[str, Any] | None = None,
    required: bool = True,
) -> AumOSComponent:
    return AumOSComponent(
        name=name,
        version=version,
        config=config or {},
        required=required,
    )


def _make_bundler(
    generate_docker_compose: bool = True,
) -> FullStackBundler:
    return FullStackBundler(generate_docker_compose=generate_docker_compose)


# ---------------------------------------------------------------------------
# AumOSComponent
# ---------------------------------------------------------------------------


class TestAumOSComponent:
    def test_valid_component(self) -> None:
        component = _make_component()
        assert component.name == "agentshield"
        assert component.version == "1.0.0"
        assert component.required is True

    def test_frozen(self) -> None:
        component = _make_component()
        with pytest.raises((AttributeError, TypeError)):
            component.name = "other"  # type: ignore[misc]

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            AumOSComponent(name="", version="1.0.0", config={})

    def test_empty_version_raises(self) -> None:
        with pytest.raises(ValueError, match="version must not be empty"):
            AumOSComponent(name="agentshield", version="", config={})

    def test_optional_component(self) -> None:
        component = _make_component(required=False)
        assert component.required is False

    def test_config_stored(self) -> None:
        cfg = {"log_level": "INFO", "max_retries": 3}
        component = _make_component(config=cfg)
        assert component.config == cfg


# ---------------------------------------------------------------------------
# FullStackBundle properties
# ---------------------------------------------------------------------------


class TestFullStackBundleProperties:
    def _build_bundle(self) -> FullStackBundle:
        bundler = _make_bundler()
        return bundler.bundle(
            "test-agent",
            [_make_component("agentshield"), _make_component("trusted-mcp")],
        )

    def test_component_names(self) -> None:
        bundle = self._build_bundle()
        names = bundle.component_names
        assert "agentshield" in names
        assert "trusted-mcp" in names

    def test_required_components_filter(self) -> None:
        bundler = _make_bundler()
        components = [
            _make_component("agentshield", required=True),
            _make_component("trusted-mcp", required=False),
        ]
        bundle = bundler.bundle("agent", components)
        required_names = [c.name for c in bundle.required_components]
        assert "agentshield" in required_names
        assert "trusted-mcp" not in required_names

    def test_optional_components_filter(self) -> None:
        bundler = _make_bundler()
        components = [
            _make_component("agentshield", required=True),
            _make_component("trusted-mcp", required=False),
        ]
        bundle = bundler.bundle("agent", components)
        optional_names = [c.name for c in bundle.optional_components]
        assert "trusted-mcp" in optional_names
        assert "agentshield" not in optional_names

    def test_bundle_is_frozen(self) -> None:
        bundle = self._build_bundle()
        with pytest.raises((AttributeError, TypeError)):
            bundle.agent_name = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FullStackBundler.bundle()
# ---------------------------------------------------------------------------


class TestFullStackBundlerBundle:
    def test_basic_bundle_created(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agentshield")],
        )
        assert bundle.agent_name == "my-agent"
        assert "agentshield" in bundle.component_names

    def test_transitive_dependencies_included(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agent-memory")],
        )
        # agent-memory depends on agentcore-sdk
        assert "agentcore-sdk" in bundle.component_names

    def test_agentcore_before_agent_memory_in_components(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agent-memory")],
        )
        names = bundle.component_names
        assert names.index("agentcore-sdk") < names.index("agent-memory")

    def test_environment_vars_propagated(self) -> None:
        bundler = _make_bundler()
        env = {"OPENAI_API_KEY": "sk-test", "LOG_LEVEL": "DEBUG"}
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agentshield")],
            environment_vars=env,
        )
        assert bundle.environment_vars == env

    def test_default_entry_point(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("my-agent", [_make_component("agentshield")])
        assert bundle.entry_point == "main.py"

    def test_custom_entry_point(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agentshield")],
            entry_point="agent/run.py",
        )
        assert bundle.entry_point == "agent/run.py"

    def test_docker_compose_generated_by_default(self) -> None:
        bundler = _make_bundler(generate_docker_compose=True)
        bundle = bundler.bundle("my-agent", [_make_component("agentshield")])
        assert bundle.docker_compose is not None
        assert "version:" in bundle.docker_compose

    def test_docker_compose_none_when_disabled(self) -> None:
        bundler = _make_bundler(generate_docker_compose=False)
        bundle = bundler.bundle("my-agent", [_make_component("agentshield")])
        assert bundle.docker_compose is None

    def test_requirements_txt_embedded(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("my-agent", [_make_component("agentshield")])
        assert "agentshield" in bundle.requirements_txt

    def test_created_at_is_utc(self) -> None:
        import datetime
        bundler = _make_bundler()
        bundle = bundler.bundle("my-agent", [_make_component("agentshield")])
        assert bundle.created_at.tzinfo == datetime.timezone.utc

    def test_empty_agent_name_raises(self) -> None:
        bundler = _make_bundler()
        with pytest.raises(ValueError, match="agent_name must not be empty"):
            bundler.bundle("", [_make_component("agentshield")])

    def test_empty_components_list_produces_bundle(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("empty-agent", [])
        assert bundle.agent_name == "empty-agent"
        assert bundle.components == ()

    def test_multiple_components_deduplicated_agentcore(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [
                _make_component("agent-memory"),
                _make_component("agent-gov"),
            ],
        )
        names = bundle.component_names
        assert names.count("agentcore-sdk") == 1

    def test_docker_compose_contains_agent_name(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("my-special-agent", [_make_component("agentshield")])
        assert bundle.docker_compose is not None
        assert "my-special-agent" in bundle.docker_compose

    def test_docker_compose_contains_entry_point(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agentshield")],
            entry_point="run.py",
        )
        assert bundle.docker_compose is not None
        assert "run.py" in bundle.docker_compose

    def test_env_vars_in_docker_compose(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle(
            "my-agent",
            [_make_component("agentshield")],
            environment_vars={"MY_VAR": "value123"},
        )
        assert bundle.docker_compose is not None
        assert "MY_VAR=value123" in bundle.docker_compose

    def test_custom_resolver_used(self) -> None:
        custom_resolver = DependencyResolver(
            extra_packages={"custom-pkg": ["agentcore-sdk"]}
        )
        bundler = FullStackBundler(resolver=custom_resolver, generate_docker_compose=False)
        bundle = bundler.bundle(
            "custom-agent",
            [_make_component("custom-pkg")],
        )
        assert "custom-pkg" in bundle.component_names
        assert "agentcore-sdk" in bundle.component_names


# ---------------------------------------------------------------------------
# export_to_directory
# ---------------------------------------------------------------------------


class TestExportToDirectory:
    def test_requirements_txt_written(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            bundler.export_to_directory(bundle, output_dir)
            req_file = output_dir / "requirements.txt"
            assert req_file.exists()
            content = req_file.read_text(encoding="utf-8")
            assert "agentshield" in content

    def test_docker_compose_written(self) -> None:
        bundler = _make_bundler(generate_docker_compose=True)
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            bundler.export_to_directory(bundle, output_dir)
            compose_file = output_dir / "docker-compose.yml"
            assert compose_file.exists()

    def test_docker_compose_not_written_when_none(self) -> None:
        bundler = _make_bundler(generate_docker_compose=False)
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            bundler.export_to_directory(bundle, output_dir)
            compose_file = output_dir / "docker-compose.yml"
            assert not compose_file.exists()

    def test_bundle_info_written(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            bundler.export_to_directory(bundle, output_dir)
            info_file = output_dir / "bundle_info.txt"
            assert info_file.exists()
            content = info_file.read_text(encoding="utf-8")
            assert "export-agent" in content

    def test_output_dir_created_if_absent(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "nested" / "dir"
            assert not output_dir.exists()
            bundler.export_to_directory(bundle, output_dir)
            assert output_dir.exists()

    def test_returns_resolved_path(self) -> None:
        bundler = _make_bundler()
        bundle = bundler.bundle("export-agent", [_make_component("agentshield")])
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            result = bundler.export_to_directory(bundle, output_dir)
            assert result.is_absolute()
