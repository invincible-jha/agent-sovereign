"""Convenience API for agent-sovereign — 3-line quickstart.

Example
-------
::

    from agent_sovereign import Bundler
    bundler = Bundler()
    bundle = bundler.bundle({"agent_id": "my-agent", "model": "gpt-4o"})

"""
from __future__ import annotations

from typing import Any


class Bundler:
    """Zero-config sovereign deployment bundler for the 80% use case.

    Wraps DeploymentPackager and SovereigntyAssessor to create a
    self-contained deployment package from a simple agent config dict.

    Example
    -------
    ::

        from agent_sovereign import Bundler
        bundler = Bundler()
        bundle = bundler.bundle({
            "agent_id": "my-assistant",
            "model": "gpt-4o",
            "data_types": ["public"],
        })
        print(bundle.sovereignty_level)
    """

    def __init__(self) -> None:
        from agent_sovereign.classifier.assessor import SovereigntyAssessor
        from agent_sovereign.classifier.levels import SovereigntyLevel
        from agent_sovereign.deployment.packager import DeploymentPackager

        self._assessor = SovereigntyAssessor()
        self._default_level = SovereigntyLevel.L1_CLOUD
        self._packager = DeploymentPackager(self._default_level)

    def bundle(self, agent_config: dict[str, Any]) -> "BundleResult":
        """Create a deployment bundle from an agent configuration dict.

        Parameters
        ----------
        agent_config:
            Agent configuration. Supported keys: ``agent_id`` (str),
            ``model`` (str), ``data_types`` (list[str]),
            ``regulations`` (list[str]).

        Returns
        -------
        BundleResult
            A thin result wrapper with ``.sovereignty_level``,
            ``.manifest``, and ``.package`` attributes.

        Example
        -------
        ::

            bundler = Bundler()
            bundle = bundler.bundle({"agent_id": "demo", "model": "gpt-4o"})
            print(bundle.sovereignty_level.name)
        """
        data_types: list[str] = agent_config.get("data_types", ["public"])
        regulations: list[str] = agent_config.get("regulations", [])

        assessment = self._assessor.assess(
            data_types=data_types,
            regulations=regulations,
        )

        packager = type(self._packager)(assessment.level)
        # Package from current working directory without requiring files
        package = packager.package(source_directory=None, explicit_files=[])

        return BundleResult(
            sovereignty_level=assessment.level,
            assessment=assessment,
            package=package,
        )

    @property
    def assessor(self) -> Any:
        """The underlying SovereigntyAssessor instance."""
        return self._assessor

    def __repr__(self) -> str:
        return "Bundler(assessor=SovereigntyAssessor)"


class BundleResult:
    """Result of a Bundler.bundle() call.

    Attributes
    ----------
    sovereignty_level:
        Assessed SovereigntyLevel for the agent config.
    assessment:
        Full SovereigntyAssessment object.
    package:
        DeploymentPackage with manifest and artifacts.
    """

    def __init__(
        self,
        sovereignty_level: Any,
        assessment: Any,
        package: Any,
    ) -> None:
        self.sovereignty_level = sovereignty_level
        self.assessment = assessment
        self.package = package

    def __repr__(self) -> str:
        return (
            f"BundleResult(sovereignty_level={self.sovereignty_level.name!r})"
        )
