"""Tests for the DependencyResolver module.

Covers:
- Known package catalogue
- Transitive dependency expansion
- Topological sort ordering (dependencies before dependents)
- Conflict detection (empty conflict list by default)
- requirements.txt generation
- Unknown package pass-through
- Edge cases: empty input, single package with no deps, cycles
"""
from __future__ import annotations

import pytest

from agent_sovereign.bundler.dependency_resolver import (
    DependencyConflictError,
    DependencyResolver,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver() -> DependencyResolver:
    return DependencyResolver()


# ---------------------------------------------------------------------------
# Basic resolution
# ---------------------------------------------------------------------------


class TestResolveBasic:
    def test_empty_request_returns_empty(self, resolver: DependencyResolver) -> None:
        result = resolver.resolve([])
        assert result == []

    def test_package_with_no_deps_returns_itself(self, resolver: DependencyResolver) -> None:
        result = resolver.resolve(["agentshield"])
        assert result == ["agentshield"]

    def test_agentcore_included_as_transitive_dep(self, resolver: DependencyResolver) -> None:
        result = resolver.resolve(["agent-memory"])
        assert "agentcore-sdk" in result
        assert "agent-memory" in result

    def test_agentcore_comes_before_agent_memory(self, resolver: DependencyResolver) -> None:
        result = resolver.resolve(["agent-memory"])
        assert result.index("agentcore-sdk") < result.index("agent-memory")

    def test_agentcore_comes_before_agent_gov(self, resolver: DependencyResolver) -> None:
        result = resolver.resolve(["agent-gov"])
        assert result.index("agentcore-sdk") < result.index("agent-gov")

    def test_multiple_packages_share_agentcore_deduplicated(
        self, resolver: DependencyResolver
    ) -> None:
        result = resolver.resolve(["agent-memory", "agent-gov"])
        # agentcore-sdk should appear exactly once
        assert result.count("agentcore-sdk") == 1

    def test_all_requested_packages_present_in_result(
        self, resolver: DependencyResolver
    ) -> None:
        requested = ["agent-memory", "agentshield", "trusted-mcp"]
        result = resolver.resolve(requested)
        for package in requested:
            assert package in result

    def test_resolve_multiple_deps_correct_order(
        self, resolver: DependencyResolver
    ) -> None:
        result = resolver.resolve(["agent-identity", "agent-observability"])
        # Both depend on agentcore-sdk which must come first
        idx_agentcore = result.index("agentcore-sdk")
        idx_identity = result.index("agent-identity")
        idx_observability = result.index("agent-observability")
        assert idx_agentcore < idx_identity
        assert idx_agentcore < idx_observability


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


class TestCheckConflicts:
    def test_no_conflicts_by_default(self, resolver: DependencyResolver) -> None:
        packages = ["agent-memory", "agent-gov", "agentcore-sdk"]
        conflicts = resolver.check_conflicts(packages)
        assert conflicts == []

    def test_empty_packages_no_conflicts(self, resolver: DependencyResolver) -> None:
        assert resolver.check_conflicts([]) == []


# ---------------------------------------------------------------------------
# Requirements generation
# ---------------------------------------------------------------------------


class TestGenerateRequirements:
    def test_output_starts_with_comment(self, resolver: DependencyResolver) -> None:
        output = resolver.generate_requirements(["agentshield"])
        assert output.startswith("# Auto-generated")

    def test_known_packages_have_aumos_annotation(
        self, resolver: DependencyResolver
    ) -> None:
        output = resolver.generate_requirements(["agentshield"])
        assert "agentshield  # aumos" in output

    def test_unknown_packages_emitted_without_annotation(
        self, resolver: DependencyResolver
    ) -> None:
        output = resolver.generate_requirements(["requests==2.31.0"])
        assert "requests==2.31.0" in output
        assert "# aumos" not in output.split("requests==2.31.0")[1].split("\n")[0]

    def test_multiple_packages_all_present(self, resolver: DependencyResolver) -> None:
        packages = ["agentcore-sdk", "agent-memory"]
        output = resolver.generate_requirements(packages)
        assert "agentcore-sdk" in output
        assert "agent-memory" in output

    def test_empty_list_returns_only_header(self, resolver: DependencyResolver) -> None:
        output = resolver.generate_requirements([])
        assert "agentshield" not in output
        assert "# Auto-generated" in output

    def test_output_ends_with_newline(self, resolver: DependencyResolver) -> None:
        output = resolver.generate_requirements(["agentshield"])
        assert output.endswith("\n")


# ---------------------------------------------------------------------------
# is_known_package / list_known_packages
# ---------------------------------------------------------------------------


class TestPackageCatalogue:
    def test_agentcore_is_known(self, resolver: DependencyResolver) -> None:
        assert resolver.is_known_package("agentcore-sdk") is True

    def test_agent_memory_is_known(self, resolver: DependencyResolver) -> None:
        assert resolver.is_known_package("agent-memory") is True

    def test_unknown_package_is_not_known(self, resolver: DependencyResolver) -> None:
        assert resolver.is_known_package("some-random-lib") is False

    def test_list_known_packages_is_sorted(self, resolver: DependencyResolver) -> None:
        known = resolver.list_known_packages()
        assert known == sorted(known)

    def test_list_known_packages_includes_agentcore(
        self, resolver: DependencyResolver
    ) -> None:
        assert "agentcore-sdk" in resolver.list_known_packages()


# ---------------------------------------------------------------------------
# Extra packages (constructor injection)
# ---------------------------------------------------------------------------


class TestExtraPackages:
    def test_extra_package_resolved(self) -> None:
        resolver = DependencyResolver(
            extra_packages={"my-plugin": ["agentcore-sdk"]}
        )
        result = resolver.resolve(["my-plugin"])
        assert "my-plugin" in result
        assert "agentcore-sdk" in result

    def test_extra_package_recognised_as_known(self) -> None:
        resolver = DependencyResolver(
            extra_packages={"custom-pkg": []}
        )
        assert resolver.is_known_package("custom-pkg") is True

    def test_repr_contains_count(self) -> None:
        resolver = DependencyResolver()
        representation = repr(resolver)
        assert "DependencyResolver" in representation
        assert "known_packages=" in representation
