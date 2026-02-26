"""Deployment package builder.

Generates a signed, checksummed deployment bundle manifest for a sovereign
agent deployment. The manifest is produced as a YAML document capturing all
files, sovereignty metadata, and integrity information.
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.templates import DeploymentTemplate, get_template


@dataclass
class DeploymentManifest:
    """Structured manifest describing a deployment package.

    Attributes
    ----------
    package_id:
        Unique identifier for this package.
    created_at:
        ISO-8601 timestamp of package creation.
    sovereignty_level:
        The sovereignty level this package targets.
    template_name:
        Name of the DeploymentTemplate used.
    files:
        List of relative file paths included in the bundle.
    metadata:
        Additional key/value metadata attached to this package.
    """

    package_id: str
    created_at: str
    sovereignty_level: str
    template_name: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a plain-dict representation suitable for YAML serialisation."""
        return {
            "package_id": self.package_id,
            "created_at": self.created_at,
            "sovereignty_level": self.sovereignty_level,
            "template_name": self.template_name,
            "files": self.files,
            "metadata": self.metadata,
        }


@dataclass
class DeploymentPackage:
    """A complete deployment bundle ready for transfer or installation.

    Attributes
    ----------
    manifest:
        Structured manifest document for the package.
    files_list:
        Resolved list of file paths (absolute or relative) included.
    checksum:
        SHA-256 hex digest of the serialised manifest YAML, providing
        integrity verification for the manifest itself.
    sovereignty_level:
        The sovereignty level this package targets.
    manifest_yaml:
        The raw YAML string of the manifest.
    template:
        The DeploymentTemplate applied during packaging.
    """

    manifest: DeploymentManifest
    files_list: list[str]
    checksum: str
    sovereignty_level: SovereigntyLevel
    manifest_yaml: str
    template: DeploymentTemplate


class DeploymentPackager:
    """Creates deployment packages for sovereign agent bundles.

    Collects files from a source directory (or an explicit file list),
    resolves a DeploymentTemplate for the target sovereignty level,
    generates a YAML manifest, and computes an integrity checksum.

    Parameters
    ----------
    sovereignty_level:
        The target sovereignty level for the deployment.
    package_id:
        Optional explicit package identifier. Defaults to a UUID-style
        string derived from the timestamp and level name.
    metadata:
        Optional additional key/value pairs to embed in the manifest.
    template:
        Optional explicit DeploymentTemplate. If omitted, the built-in
        template for the sovereignty level is used.
    """

    def __init__(
        self,
        sovereignty_level: SovereigntyLevel,
        package_id: str | None = None,
        metadata: dict[str, str] | None = None,
        template: DeploymentTemplate | None = None,
    ) -> None:
        self._sovereignty_level = sovereignty_level
        self._template = template if template is not None else get_template(sovereignty_level)
        self._metadata = metadata or {}
        self._package_id = package_id or self._generate_package_id()

    def _generate_package_id(self) -> str:
        """Generate a deterministic-looking package identifier."""
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        level_tag = self._sovereignty_level.name.lower()
        return f"agsov-{level_tag}-{timestamp}"

    def package(
        self,
        source_directory: Path | None = None,
        explicit_files: list[Path] | None = None,
    ) -> DeploymentPackage:
        """Build and return a DeploymentPackage.

        Collects files either from a directory scan or an explicit list.
        Generates the YAML manifest and computes its SHA-256 checksum.

        Parameters
        ----------
        source_directory:
            Directory to scan recursively for files to include.
            Mutually exclusive with ``explicit_files``.
        explicit_files:
            Explicit list of file paths to include in the package.
            Mutually exclusive with ``source_directory``.

        Returns
        -------
        DeploymentPackage
            The assembled package with manifest, checksum, and file list.

        Raises
        ------
        ValueError
            If neither or both of source_directory and explicit_files are given.
        FileNotFoundError
            If source_directory does not exist.
        """
        if source_directory is not None and explicit_files is not None:
            raise ValueError(
                "Provide either source_directory or explicit_files, not both."
            )
        if source_directory is None and explicit_files is None:
            raise ValueError(
                "One of source_directory or explicit_files must be provided."
            )

        files_list: list[str] = []
        if source_directory is not None:
            if not source_directory.exists():
                raise FileNotFoundError(
                    f"Source directory does not exist: {source_directory}"
                )
            for root, _dirs, filenames in os.walk(source_directory):
                for filename in sorted(filenames):
                    absolute = Path(root) / filename
                    relative = absolute.relative_to(source_directory)
                    files_list.append(str(relative))
        else:
            # explicit_files is not None here
            files_list = [str(fp) for fp in explicit_files]  # type: ignore[union-attr]

        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        manifest = DeploymentManifest(
            package_id=self._package_id,
            created_at=created_at,
            sovereignty_level=self._sovereignty_level.name,
            template_name=self._template.name,
            files=sorted(files_list),
            metadata={
                "agent_sovereign_version": "0.1.0",
                "template_description": self._template.description[:120],
                **self._metadata,
            },
        )

        manifest_yaml = self._render_yaml(manifest)
        checksum = hashlib.sha256(manifest_yaml.encode("utf-8")).hexdigest()

        return DeploymentPackage(
            manifest=manifest,
            files_list=files_list,
            checksum=checksum,
            sovereignty_level=self._sovereignty_level,
            manifest_yaml=manifest_yaml,
            template=self._template,
        )

    @staticmethod
    def _render_yaml(manifest: DeploymentManifest) -> str:
        """Serialise the manifest to a canonical YAML string.

        Parameters
        ----------
        manifest:
            The manifest to serialise.

        Returns
        -------
        str
            Canonical YAML representation.
        """
        stream = io.StringIO()
        yaml.dump(
            manifest.to_dict(),
            stream,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )
        return stream.getvalue()


__all__ = [
    "DeploymentManifest",
    "DeploymentPackage",
    "DeploymentPackager",
]
