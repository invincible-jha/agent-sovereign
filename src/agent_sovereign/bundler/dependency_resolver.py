"""AumOS package dependency resolver for full-stack bundling.

Resolves transitive dependencies for a given set of AumOS package names,
performs conflict detection, and generates requirements.txt content.

The resolver uses a simple topological sort (Kahn's algorithm) over a
directed acyclic dependency graph.  All AumOS package names are treated
as known packages with declared dependency lists.  Unknown packages are
passed through with a warning so that third-party pip packages work.

Classes
-------
- DependencyConflictError   Raised when irreconcilable conflicts are found.
- DependencyResolver        Resolve, validate, and emit requirements for bundles.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import ClassVar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DependencyConflictError(Exception):
    """Raised when conflicting package requirements are detected."""


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class DependencyResolver:
    """Resolves AumOS package dependencies for bundling.

    All AumOS packages have their dependency lists declared in
    :attr:`KNOWN_PACKAGES`.  The resolver performs a topological sort so
    that packages are listed in dependency-first order (dependencies appear
    before the packages that require them).

    Parameters
    ----------
    extra_packages:
        Additional package name→dependency-list entries to augment
        ``KNOWN_PACKAGES``.  Useful for testing and for edge-case packages
        not yet in the main catalogue.
    """

    #: Map of AumOS package name → list of direct dependency package names.
    KNOWN_PACKAGES: ClassVar[dict[str, list[str]]] = {
        "agent-memory": ["agentcore-sdk"],
        "agent-gov": ["agentcore-sdk"],
        "agent-identity": ["agentcore-sdk"],
        "agent-observability": ["agentcore-sdk"],
        "agentshield": [],
        "trusted-mcp": [],
        "agentcore-sdk": [],
        "agent-eval": ["agentcore-sdk"],
        "agent-mesh-router": ["agentcore-sdk"],
        "agent-session-linker": ["agentcore-sdk"],
        "agent-marketplace": ["agentcore-sdk"],
        "agent-sim-bridge": ["agentcore-sdk"],
        "agent-sovereign": ["agentcore-sdk"],
        "agent-energy-budget": ["agentcore-sdk"],
        "agent-sense": ["agentcore-sdk"],
        "agent-vertical": ["agentcore-sdk"],
    }

    #: Packages that cannot be used together (mutually exclusive pairs).
    _CONFLICTS: ClassVar[list[frozenset[str]]] = []

    def __init__(
        self,
        extra_packages: dict[str, list[str]] | None = None,
    ) -> None:
        self._package_graph: dict[str, list[str]] = dict(self.KNOWN_PACKAGES)
        if extra_packages:
            self._package_graph.update(extra_packages)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, requested: list[str]) -> list[str]:
        """Return a topologically sorted list of all packages to install.

        Transitively expands dependencies so the result includes every
        package needed to satisfy *requested*.  The ordering guarantees
        that a package's dependencies appear before it in the list.

        Parameters
        ----------
        requested:
            Package names explicitly requested by the caller.

        Returns
        -------
        list[str]
            Topologically sorted list of package names (dependencies first).

        Raises
        ------
        DependencyConflictError
            If conflicts are detected among the resolved packages.
        """
        # Expand transitive dependencies
        all_packages = self._expand_transitive(requested)

        # Check conflicts before emitting
        conflicts = self.check_conflicts(all_packages)
        if conflicts:
            raise DependencyConflictError(
                f"Dependency conflicts detected: {conflicts}"
            )

        # Topological sort
        return self._topological_sort(all_packages)

    def check_conflicts(self, packages: list[str]) -> list[str]:
        """Return a list of conflict descriptions for *packages*.

        Parameters
        ----------
        packages:
            List of package names to check.

        Returns
        -------
        list[str]
            Human-readable conflict descriptions.  Empty list means no
            conflicts.
        """
        package_set = set(packages)
        conflict_messages: list[str] = []
        for conflict_pair in self._CONFLICTS:
            if conflict_pair.issubset(package_set):
                names = sorted(conflict_pair)
                conflict_messages.append(
                    f"Packages {names[0]!r} and {names[1]!r} cannot be used together."
                )
        return conflict_messages

    def generate_requirements(self, packages: list[str]) -> str:
        """Generate a requirements.txt string for the given package list.

        Each AumOS package is emitted as a ``# aumos`` annotated line.
        Unknown packages (not in :attr:`KNOWN_PACKAGES` or extras) are
        emitted as-is without annotation.

        Parameters
        ----------
        packages:
            Ordered list of package names (ideally from :meth:`resolve`).

        Returns
        -------
        str
            A requirements.txt-formatted string suitable for ``pip install``.
        """
        lines: list[str] = [
            "# Auto-generated by AumOS DependencyResolver",
            "# Do not edit — regenerate via FullStackBundler",
            "",
        ]
        for package in packages:
            if package in self._package_graph:
                lines.append(f"{package}  # aumos")
            else:
                lines.append(package)
        return "\n".join(lines) + "\n"

    def is_known_package(self, package_name: str) -> bool:
        """Return True if *package_name* is a known AumOS package."""
        return package_name in self._package_graph

    def list_known_packages(self) -> list[str]:
        """Return sorted list of all known AumOS package names."""
        return sorted(self._package_graph)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _expand_transitive(self, requested: list[str]) -> list[str]:
        """BFS-expand *requested* to include all transitive dependencies.

        Parameters
        ----------
        requested:
            Seed package names.

        Returns
        -------
        list[str]
            All packages (requested + transitive) in discovery order.
            Duplicates are removed while preserving first-encounter order.
        """
        seen: set[str] = set()
        order: list[str] = []
        queue: deque[str] = deque(requested)

        while queue:
            package = queue.popleft()
            if package in seen:
                continue
            seen.add(package)
            order.append(package)

            deps = self._package_graph.get(package, [])
            if deps:
                logger.debug(
                    "DependencyResolver: %r → deps=%r", package, deps
                )
            for dep in deps:
                if dep not in seen:
                    queue.append(dep)

        return order

    def _topological_sort(self, packages: list[str]) -> list[str]:
        """Topologically sort *packages* using Kahn's algorithm.

        Only edges between packages present in *packages* are considered.

        Parameters
        ----------
        packages:
            List of package names to sort.

        Returns
        -------
        list[str]
            Dependency-first ordering of *packages*.
        """
        package_set = set(packages)

        # Build adjacency and in-degree for packages in scope
        in_degree: dict[str, int] = {p: 0 for p in packages}
        adjacency: dict[str, list[str]] = {p: [] for p in packages}

        for package in packages:
            deps = self._package_graph.get(package, [])
            for dep in deps:
                if dep in package_set:
                    # dep → package edge means dep must come before package
                    adjacency[dep].append(package)
                    in_degree[package] += 1

        # Kahn's BFS
        queue: deque[str] = deque(
            sorted(p for p, deg in in_degree.items() if deg == 0)
        )
        sorted_packages: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_packages.append(node)
            for successor in sorted(adjacency[node]):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(sorted_packages) != len(packages):
            # Cycle detected — fall back to original order with a warning
            logger.warning(
                "DependencyResolver: cycle detected in dependency graph — "
                "falling back to discovery order."
            )
            return packages

        return sorted_packages

    def __repr__(self) -> str:
        return f"DependencyResolver(known_packages={len(self._package_graph)})"


__all__ = [
    "DependencyConflictError",
    "DependencyResolver",
]
