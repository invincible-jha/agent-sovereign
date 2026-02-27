"""Full-stack agent bundler — combines agent + memory + governance + identity.

Produces a self-contained :class:`FullStackBundle` that declares every
AumOS component required for a production deployment, resolves transitive
dependencies, renders a ``requirements.txt``, and optionally generates a
``docker-compose.yml``.

Classes
-------
- AumOSComponent       Value object for a single AumOS component in a bundle.
- FullStackBundle      Immutable record of a complete resolved bundle.
- FullStackBundler     Builder: combines components → FullStackBundle.
"""
from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_sovereign.bundler.dependency_resolver import DependencyResolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AumOSComponent:
    """A single AumOS component to be included in a full-stack bundle.

    Attributes
    ----------
    name:
        AumOS package name, e.g. ``"agent-memory"``, ``"agent-gov"``.
    version:
        Package version string, e.g. ``"1.0.0"`` or ``">=0.3,<1"``.
    config:
        Component-specific configuration key/value pairs.  Must be
        JSON-serialisable.
    required:
        Whether the component is mandatory for the bundle to function.
        Optional components may be omitted at runtime without breaking
        the agent.
    """

    name: str
    version: str
    config: dict[str, object]
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AumOSComponent.name must not be empty.")
        if not self.version:
            raise ValueError("AumOSComponent.version must not be empty.")


@dataclass(frozen=True)
class FullStackBundle:
    """Immutable record of a complete, resolved full-stack agent bundle.

    Attributes
    ----------
    agent_name:
        Human-readable name for the agent being bundled.
    components:
        Ordered tuple of :class:`AumOSComponent` instances included in
        the bundle (after dependency resolution).
    entry_point:
        Relative path to the agent entry-point script (e.g. ``"main.py"``).
    environment_vars:
        Environment variables that must be set when running the agent.
    docker_compose:
        Rendered docker-compose YAML string, or ``None`` if Docker
        generation was skipped.
    requirements_txt:
        Rendered ``requirements.txt`` content string.
    created_at:
        UTC timestamp of when the bundle was created.
    """

    agent_name: str
    components: tuple[AumOSComponent, ...]
    entry_point: str
    environment_vars: dict[str, str]
    docker_compose: str | None
    requirements_txt: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.agent_name:
            raise ValueError("FullStackBundle.agent_name must not be empty.")
        if not self.entry_point:
            raise ValueError("FullStackBundle.entry_point must not be empty.")

    @property
    def component_names(self) -> list[str]:
        """Return the list of component names in this bundle."""
        return [c.name for c in self.components]

    @property
    def required_components(self) -> list[AumOSComponent]:
        """Return only the required components."""
        return [c for c in self.components if c.required]

    @property
    def optional_components(self) -> list[AumOSComponent]:
        """Return only the optional components."""
        return [c for c in self.components if not c.required]


# ---------------------------------------------------------------------------
# Bundler
# ---------------------------------------------------------------------------


class FullStackBundler:
    """Creates self-contained agent bundles with all AumOS components.

    Orchestrates dependency resolution, requirements generation, and
    optional docker-compose generation to produce a :class:`FullStackBundle`.

    Parameters
    ----------
    resolver:
        Optional custom :class:`DependencyResolver`.  A default instance
        is created if ``None``.
    generate_docker_compose:
        If ``True`` (default), a ``docker-compose.yml`` is rendered and
        embedded in the bundle.
    python_version:
        Python version string used in generated Docker configurations
        (e.g. ``"3.11"``).
    """

    def __init__(
        self,
        resolver: DependencyResolver | None = None,
        generate_docker_compose: bool = True,
        python_version: str = "3.11",
    ) -> None:
        self._resolver = resolver if resolver is not None else DependencyResolver()
        self._generate_docker_compose = generate_docker_compose
        self._python_version = python_version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bundle(
        self,
        agent_name: str,
        components: list[AumOSComponent],
        entry_point: str = "main.py",
        environment_vars: dict[str, str] | None = None,
    ) -> FullStackBundle:
        """Assemble a full-stack bundle from a list of AumOS components.

        Dependency resolution is performed automatically — all transitive
        dependencies of the supplied *components* are included.

        Parameters
        ----------
        agent_name:
            Human-readable name for the agent.
        components:
            Explicit AumOS components to include.  Their transitive
            dependencies are resolved and added automatically.
        entry_point:
            Relative path to the agent entry-point file.
        environment_vars:
            Environment variables that the agent needs at runtime.
            Defaults to an empty dict.

        Returns
        -------
        FullStackBundle
            Fully resolved, immutable bundle record.
        """
        if not agent_name:
            raise ValueError("agent_name must not be empty.")

        resolved_env_vars: dict[str, str] = dict(environment_vars or {})
        requested_names = [c.name for c in components]

        try:
            resolved_names = self._resolver.resolve(requested_names)
        except Exception as exc:
            logger.error("FullStackBundler: dependency resolution failed: %s", exc)
            raise

        # Merge resolved order — keep original component configs for known ones
        component_config_map = {c.name: c for c in components}
        resolved_components: list[AumOSComponent] = []

        for package_name in resolved_names:
            if package_name in component_config_map:
                resolved_components.append(component_config_map[package_name])
            else:
                # Transitive dependency — create a minimal AumOSComponent
                resolved_components.append(
                    AumOSComponent(
                        name=package_name,
                        version="latest",
                        config={},
                        required=True,
                    )
                )

        requirements_txt = self._generate_requirements(resolved_components)

        # Create a preliminary bundle for docker-compose generation
        preliminary = FullStackBundle(
            agent_name=agent_name,
            components=tuple(resolved_components),
            entry_point=entry_point,
            environment_vars=resolved_env_vars,
            docker_compose=None,
            requirements_txt=requirements_txt,
            created_at=datetime.now(tz=timezone.utc),
        )

        docker_compose: str | None = None
        if self._generate_docker_compose:
            docker_compose = self._generate_docker_compose_content(preliminary)

        bundle = FullStackBundle(
            agent_name=agent_name,
            components=tuple(resolved_components),
            entry_point=entry_point,
            environment_vars=resolved_env_vars,
            docker_compose=docker_compose,
            requirements_txt=requirements_txt,
            created_at=preliminary.created_at,
        )

        logger.info(
            "FullStackBundler: bundled %r with %d components.",
            agent_name,
            len(resolved_components),
        )
        return bundle

    def export_to_directory(
        self,
        bundle: FullStackBundle,
        output_dir: Path,
    ) -> Path:
        """Write bundle artefacts to *output_dir* and return the directory path.

        Files written:
        - ``requirements.txt`` — Python package requirements.
        - ``docker-compose.yml`` — Docker Compose file (if generated).
        - ``bundle_info.txt`` — Human-readable bundle summary.

        Parameters
        ----------
        bundle:
            The :class:`FullStackBundle` to export.
        output_dir:
            Target directory.  Created if it does not exist.

        Returns
        -------
        Path
            The resolved *output_dir* path.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        req_path = output_dir / "requirements.txt"
        req_path.write_text(bundle.requirements_txt, encoding="utf-8")
        logger.debug("FullStackBundler: wrote %s", req_path)

        if bundle.docker_compose is not None:
            compose_path = output_dir / "docker-compose.yml"
            compose_path.write_text(bundle.docker_compose, encoding="utf-8")
            logger.debug("FullStackBundler: wrote %s", compose_path)

        info_path = output_dir / "bundle_info.txt"
        info_path.write_text(self._render_bundle_info(bundle), encoding="utf-8")
        logger.debug("FullStackBundler: wrote %s", info_path)

        return output_dir.resolve()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_requirements(self, components: list[AumOSComponent]) -> str:
        """Render a requirements.txt string from resolved components.

        Parameters
        ----------
        components:
            List of AumOS components in dependency-first order.

        Returns
        -------
        str
            Requirements file content.
        """
        package_names = [c.name for c in components]
        return self._resolver.generate_requirements(package_names)

    def _generate_docker_compose_content(self, bundle: FullStackBundle) -> str:
        """Render a docker-compose YAML string for *bundle*.

        Parameters
        ----------
        bundle:
            The bundle to render Docker Compose configuration for.

        Returns
        -------
        str
            YAML-formatted docker-compose content.
        """
        # Sanitise agent name for use as a YAML key / container name
        safe_name = bundle.agent_name.lower().replace(" ", "-").replace("_", "-")

        env_block = ""
        if bundle.environment_vars:
            env_lines = [f"      - {k}={v}" for k, v in sorted(bundle.environment_vars.items())]
            env_block = "    environment:\n" + "\n".join(env_lines) + "\n"

        component_comments = "\n".join(
            f"      # {c.name}=={c.version}"
            for c in bundle.components
        )

        compose = textwrap.dedent(f"""\
            # Auto-generated docker-compose — AumOS FullStackBundler
            # Agent: {bundle.agent_name}
            # Components:
            {component_comments}
            version: "3.9"
            services:
              {safe_name}:
                build:
                  context: .
                  dockerfile: Dockerfile
                image: {safe_name}:latest
                command: python {bundle.entry_point}
            {env_block}\
            """)
        return compose

    @staticmethod
    def _render_bundle_info(bundle: FullStackBundle) -> str:
        """Render a human-readable bundle summary string."""
        lines = [
            f"Agent: {bundle.agent_name}",
            f"Entry point: {bundle.entry_point}",
            f"Created at: {bundle.created_at.isoformat()}",
            f"Components ({len(bundle.components)}):",
        ]
        for component in bundle.components:
            req_label = "required" if component.required else "optional"
            lines.append(f"  - {component.name}=={component.version} [{req_label}]")
        if bundle.environment_vars:
            lines.append("Environment variables:")
            for key in sorted(bundle.environment_vars):
                lines.append(f"  - {key}")
        return "\n".join(lines) + "\n"


__all__ = [
    "AumOSComponent",
    "FullStackBundle",
    "FullStackBundler",
]
