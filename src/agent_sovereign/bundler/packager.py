"""Agent packager — scans source directories and builds BundleManifests.

The AgentPackager is the primary entry point for the bundling pipeline.
It:

1. Walks the source directory recursively.
2. Classifies each file as one of the known component types.
3. Computes SHA-256 checksums for all included files.
4. Constructs a BundleManifest.
5. Validates the resulting manifest for completeness.

Classes
-------
- PackageConfig   Frozen dataclass of packaging options.
- AgentPackager   Stateful packager (holds config, exposes all operations).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from agent_sovereign.bundler.manifest import (
    BundleComponent,
    BundleManifest,
    BundleSovereigntyLevel,
)


# ---------------------------------------------------------------------------
# Component-type heuristics
# ---------------------------------------------------------------------------

# Maps file extension patterns to component_type strings.
# Longer / more specific patterns are checked first.
_EXTENSION_TYPE_MAP: list[tuple[frozenset[str], str]] = [
    # Model weight formats
    (
        frozenset({".gguf", ".ggml", ".bin", ".pt", ".pth", ".onnx", ".safetensors"}),
        "model",
    ),
    # Policy documents
    (
        frozenset({".rego", ".policy", ".cel"}),
        "policy",
    ),
    # Configuration
    (
        frozenset({".yaml", ".yml", ".toml", ".ini", ".env", ".json", ".cfg", ".conf"}),
        "config",
    ),
    # Agent code
    (
        frozenset({".py", ".js", ".ts", ".rb", ".go", ".rs", ".sh", ".bash"}),
        "agent_code",
    ),
]

# Directories that are always excluded from scanning.
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "env",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
        "htmlcov",
        "node_modules",
    }
)

# File names that are always excluded.
_EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".DS_Store",
        "Thumbs.db",
        ".coverage",
    }
)


# ---------------------------------------------------------------------------
# Configuration value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PackageConfig:
    """Configuration for the AgentPackager.

    Attributes
    ----------
    output_dir:
        Directory where the generated manifest JSON is written.
    include_model:
        Whether to include model weight files in the bundle.  Set to
        ``False`` for MINIMAL sovereignty bundles where the model is
        served externally.
    include_tests:
        Whether to include test files in the bundle.  Usually ``False``
        for production bundles.
    compress:
        Reserved flag — indicates the caller intends to compress the
        bundle after packaging.  The packager itself does not perform
        compression; that is a separate pipeline step.
    """

    output_dir: Path
    include_model: bool = True
    include_tests: bool = False
    compress: bool = False


# ---------------------------------------------------------------------------
# Packager
# ---------------------------------------------------------------------------


class AgentPackager:
    """Scans a source directory and assembles a BundleManifest.

    Parameters
    ----------
    config:
        Packaging options controlling which file types to include.
    """

    def __init__(self, config: PackageConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def package(
        self,
        source_dir: Path,
        sovereignty_level: BundleSovereigntyLevel,
        target_platform: str = "docker",
        metadata: dict[str, object] | None = None,
    ) -> BundleManifest:
        """Scan *source_dir* and build a BundleManifest.

        Parameters
        ----------
        source_dir:
            Root directory of the agent source tree.
        sovereignty_level:
            Sovereignty classification for the resulting bundle.
        target_platform:
            Deployment target (e.g. ``"docker"``, ``"kubernetes"``).
        metadata:
            Optional free-form annotations to embed in the manifest.

        Returns
        -------
        BundleManifest
            A fully populated manifest with checksums for every included
            component.

        Raises
        ------
        FileNotFoundError
            If *source_dir* does not exist.
        ValueError
            If *source_dir* is not a directory.
        """
        if not source_dir.exists():
            raise FileNotFoundError(
                f"Source directory does not exist: {source_dir}"
            )
        if not source_dir.is_dir():
            raise ValueError(
                f"source_dir must be a directory, got: {source_dir}"
            )

        components = self.scan_directory(source_dir)

        manifest = BundleManifest(
            sovereignty_level=sovereignty_level,
            target_platform=target_platform,
            metadata=dict(metadata) if metadata else {},
        )
        for component in components:
            manifest.add_component(component)

        return manifest

    def scan_directory(self, path: Path) -> list[BundleComponent]:
        """Recursively discover and classify files under *path*.

        Parameters
        ----------
        path:
            Directory to scan.

        Returns
        -------
        list[BundleComponent]
            Components sorted by their relative path string, one per
            discovered file.  Test files are excluded when
            ``config.include_tests`` is ``False``.  Model files are
            excluded when ``config.include_model`` is ``False``.
        """
        components: list[BundleComponent] = []

        for root_str, dir_names, file_names in os.walk(path):
            root = Path(root_str)

            # Prune excluded directories in-place (modifies the walk)
            dir_names[:] = [
                d for d in dir_names if d not in _EXCLUDED_DIRS
            ]

            # Skip test directories unless explicitly included
            if not self._config.include_tests:
                dir_names[:] = [
                    d for d in dir_names if d not in {"tests", "test"}
                ]

            for file_name in sorted(file_names):
                if file_name in _EXCLUDED_FILES:
                    continue

                file_path = root / file_name
                relative = file_path.relative_to(path)

                # Exclude test files by name pattern
                if not self._config.include_tests and _is_test_file(file_name):
                    continue

                component_type = _classify_file(file_path)

                # Respect model inclusion flag
                if component_type == "model" and not self._config.include_model:
                    continue

                size = file_path.stat().st_size
                checksum = self.compute_checksum(file_path)
                name = _derive_component_name(relative)

                components.append(
                    BundleComponent(
                        name=name,
                        component_type=component_type,
                        path=str(relative).replace("\\", "/"),
                        size_bytes=size,
                        checksum=checksum,
                    )
                )

        return components

    @staticmethod
    def compute_checksum(file_path: Path) -> str:
        """Compute the SHA-256 hex digest of a file.

        Reads in 64 KiB chunks for memory efficiency with large model files.

        Parameters
        ----------
        file_path:
            Path to the file.

        Returns
        -------
        str
            Lowercase hex SHA-256 digest.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(
                f"Cannot compute checksum: file not found: {file_path}"
            )
        hasher = hashlib.sha256()
        chunk_size = 65_536
        with file_path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def estimate_bundle_size(components: list[BundleComponent]) -> int:
        """Sum the size_bytes of all components.

        Parameters
        ----------
        components:
            List of BundleComponent instances.

        Returns
        -------
        int
            Total estimated size of the bundle in bytes.
        """
        return sum(c.size_bytes for c in components)

    def validate_bundle(
        self, manifest: BundleManifest, output_dir: Path
    ) -> list[str]:
        """Validate a BundleManifest and return a list of error messages.

        Checks performed:

        - Manifest has at least one component.
        - Manifest has a non-empty bundle_id.
        - Manifest has a non-empty target_platform.
        - No duplicate component names.
        - No duplicate component paths.
        - All component checksums are 64 hex characters (SHA-256).
        - All component sizes are non-negative.
        - output_dir exists (or is creatable).

        Parameters
        ----------
        manifest:
            The BundleManifest to validate.
        output_dir:
            Intended output directory for the bundle.

        Returns
        -------
        list[str]
            Zero or more human-readable error messages.  An empty list
            means the bundle passed all checks.
        """
        errors: list[str] = []

        if not manifest.bundle_id:
            errors.append("bundle_id is empty.")

        if not manifest.target_platform:
            errors.append("target_platform is empty.")

        if not manifest.components:
            errors.append("Manifest contains no components.")

        names_seen: set[str] = set()
        paths_seen: set[str] = set()
        for component in manifest.components:
            if component.name in names_seen:
                errors.append(
                    f"Duplicate component name: {component.name!r}"
                )
            names_seen.add(component.name)

            if component.path in paths_seen:
                errors.append(
                    f"Duplicate component path: {component.path!r}"
                )
            paths_seen.add(component.path)

            if len(component.checksum) != 64 or not _is_hex(component.checksum):
                errors.append(
                    f"Component {component.name!r} has an invalid checksum: "
                    f"{component.checksum!r} (expected 64 hex chars)."
                )

            if component.size_bytes < 0:
                errors.append(
                    f"Component {component.name!r} has negative size_bytes: "
                    f"{component.size_bytes}."
                )

        if output_dir.exists() and not output_dir.is_dir():
            errors.append(
                f"output_dir exists but is not a directory: {output_dir}"
            )

        return errors


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _classify_file(file_path: Path) -> str:
    """Return the component_type string for a given file.

    Defaults to ``"data"`` if no extension matches a known type.

    Parameters
    ----------
    file_path:
        Path to the file being classified.

    Returns
    -------
    str
        One of: ``"model"``, ``"agent_code"``, ``"config"``,
        ``"policy"``, ``"data"``.
    """
    suffix = file_path.suffix.lower()
    for extensions, component_type in _EXTENSION_TYPE_MAP:
        if suffix in extensions:
            return component_type
    return "data"


def _is_test_file(file_name: str) -> bool:
    """Return True if the file looks like a test module.

    Parameters
    ----------
    file_name:
        Bare file name (not a path).

    Returns
    -------
    bool
        True when the file name starts with ``test_`` or ends with
        ``_test.py``.
    """
    lower = file_name.lower()
    return lower.startswith("test_") or lower.endswith("_test.py")


def _derive_component_name(relative: Path) -> str:
    """Derive a unique, human-readable component name from a relative path.

    Uses the file stem (name without extension) joined with parent path
    segments using ``/`` for readability.

    Parameters
    ----------
    relative:
        Relative path of the file inside the bundle.

    Returns
    -------
    str
        A slash-separated name string, e.g. ``"models/llama-3-8b"``.
    """
    parts = list(relative.parts)
    if not parts:
        return "unknown"
    # Strip the extension from the final segment
    stem = Path(parts[-1]).stem
    parts[-1] = stem
    return "/".join(parts)


def _is_hex(value: str) -> bool:
    """Return True if *value* is a valid hexadecimal string.

    Parameters
    ----------
    value:
        String to test.

    Returns
    -------
    bool
        True if every character is a valid hex digit.
    """
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


__all__ = [
    "AgentPackager",
    "PackageConfig",
]
