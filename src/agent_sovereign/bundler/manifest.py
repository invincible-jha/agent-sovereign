"""Bundle manifest data model for sovereign agent deployments.

Defines the structured manifest that describes every component in a
deployment bundle, the target sovereignty level, and integrity checksums
for all included files.

Classes
-------
- BundleComponent     Value object for a single component (frozen dataclass).
- BundleSovereigntyLevel  Three-tier enum for bundle-level sovereignty.
- BundleManifest      Pydantic v2 model for the full bundle descriptor.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleComponent:
    """A single component included in a deployment bundle.

    Attributes
    ----------
    name:
        Human-readable identifier for this component (e.g. ``"llama-3-8b"``).
    component_type:
        Classification of the component.  Must be one of:
        ``"model"``, ``"agent_code"``, ``"config"``, ``"policy"``, ``"data"``.
    path:
        Relative path of the component file inside the bundle root.
    size_bytes:
        File size in bytes.
    checksum:
        SHA-256 hex digest of the file content, used for integrity verification.
    """

    name: str
    component_type: str
    path: str
    size_bytes: int
    checksum: str

    _VALID_TYPES: frozenset[str] = frozenset(
        {"model", "agent_code", "config", "policy", "data"}
    )

    def __post_init__(self) -> None:
        if self.component_type not in self._VALID_TYPES:
            raise ValueError(
                f"Invalid component_type {self.component_type!r}. "
                f"Must be one of: {sorted(self._VALID_TYPES)}"
            )
        if self.size_bytes < 0:
            raise ValueError(
                f"size_bytes must be >= 0, got {self.size_bytes}"
            )
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.path:
            raise ValueError("path must not be empty")
        if not self.checksum:
            raise ValueError("checksum must not be empty")


# ---------------------------------------------------------------------------
# Sovereignty level enum (bundle-scoped — distinct from classifier levels)
# ---------------------------------------------------------------------------


class BundleSovereigntyLevel(str, Enum):
    """Coarse sovereignty classification for a deployment bundle.

    Values
    ------
    FULL:
        Air-gapped bundle.  No external calls are permitted at runtime.
        All model weights, code, and configuration are embedded.
    PARTIAL:
        Local model with external API calls allowed for non-inference
        workloads (e.g. logging, telemetry, auxiliary services).
    MINIMAL:
        External model and external APIs.  Bundle contains only
        configuration and agent orchestration code.
    """

    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# Pydantic manifest
# ---------------------------------------------------------------------------


class BundleManifest(BaseModel):
    """Full descriptor for a sovereign agent deployment bundle.

    This is the canonical record that travels alongside a bundle archive.
    It is serialisable to / from JSON and supports in-place component
    management and checksum verification.

    Attributes
    ----------
    bundle_id:
        UUID-formatted identifier for this bundle.  Auto-generated if not
        supplied.
    created_at:
        UTC datetime of bundle creation.  Auto-set to *now* if omitted.
    sovereignty_level:
        Coarse sovereignty classification (FULL / PARTIAL / MINIMAL).
    target_platform:
        Deployment target, e.g. ``"docker"``, ``"kubernetes"``,
        ``"lambda"``, ``"edge"``.
    components:
        Ordered list of BundleComponent records.
    metadata:
        Free-form key/value pairs for environment-specific annotations.
    """

    bundle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    sovereignty_level: BundleSovereigntyLevel
    target_platform: str
    components: list[BundleComponent] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    # ------------------------------------------------------------------
    # Computed field
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[misc]
    @property
    def total_size_bytes(self) -> int:
        """Return the sum of all component sizes."""
        return self.compute_total_size()

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def add_component(self, component: BundleComponent) -> None:
        """Add a component to the manifest.

        Parameters
        ----------
        component:
            The BundleComponent to add.

        Raises
        ------
        ValueError
            If a component with the same name already exists.
        """
        existing_names = {c.name for c in self.components}
        if component.name in existing_names:
            raise ValueError(
                f"A component named {component.name!r} already exists in this manifest. "
                "Remove it first or use a unique name."
            )
        self.components.append(component)

    def remove_component(self, name: str) -> None:
        """Remove a component by name.

        Parameters
        ----------
        name:
            Name of the component to remove.

        Raises
        ------
        KeyError
            If no component with the given name exists.
        """
        original_length = len(self.components)
        self.components = [c for c in self.components if c.name != name]
        if len(self.components) == original_length:
            raise KeyError(f"No component named {name!r} found in manifest.")

    # ------------------------------------------------------------------
    # Size helpers
    # ------------------------------------------------------------------

    def compute_total_size(self) -> int:
        """Return the summed size of all components in bytes.

        Returns
        -------
        int
            Total bytes across all BundleComponent entries.
        """
        return sum(c.size_bytes for c in self.components)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Serialise the manifest to a JSON string.

        Parameters
        ----------
        indent:
            JSON indentation level.  Default: 2.

        Returns
        -------
        str
            A UTF-8 JSON string representation of the manifest.
        """
        raw = self.model_dump(mode="json")
        # Convert datetime to ISO string if Pydantic returned it as datetime
        if isinstance(raw.get("created_at"), datetime.datetime):
            raw["created_at"] = raw["created_at"].isoformat()
        return json.dumps(raw, indent=indent, default=str)

    @classmethod
    def from_json(cls, data: str) -> "BundleManifest":
        """Deserialise a manifest from a JSON string.

        Parameters
        ----------
        data:
            JSON string produced by :meth:`to_json`.

        Returns
        -------
        BundleManifest
            The reconstructed manifest instance.

        Raises
        ------
        pydantic.ValidationError
            If the JSON does not match the expected schema.
        json.JSONDecodeError
            If *data* is not valid JSON.
        """
        raw = json.loads(data)
        # Reconstruct frozen BundleComponent dataclasses from dict
        raw_components = raw.pop("components", [])
        # Remove computed field if present in serialised form
        raw.pop("total_size_bytes", None)
        manifest = cls.model_validate(raw)
        manifest.components = [
            BundleComponent(
                name=c["name"],
                component_type=c["component_type"],
                path=c["path"],
                size_bytes=c["size_bytes"],
                checksum=c["checksum"],
            )
            for c in raw_components
        ]
        return manifest

    # ------------------------------------------------------------------
    # Checksum verification
    # ------------------------------------------------------------------

    def verify_checksums(
        self, base_path: Path
    ) -> list[tuple[str, bool]]:
        """Verify all component checksums against files on disk.

        For each BundleComponent, resolve ``base_path / component.path``,
        compute its SHA-256 digest, and compare it to the stored checksum.

        Parameters
        ----------
        base_path:
            Directory under which component paths are resolved.

        Returns
        -------
        list[tuple[str, bool]]
            A list of ``(component_name, is_valid)`` pairs — one per
            component.  ``is_valid`` is ``False`` if the file is missing
            or its digest does not match.
        """
        results: list[tuple[str, bool]] = []
        for component in self.components:
            file_path = base_path / component.path
            if not file_path.exists():
                results.append((component.name, False))
                continue
            digest = _sha256_file(file_path)
            results.append((component.name, digest == component.checksum))
        return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256_file(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads in 64 KiB chunks to keep memory usage low for large model files.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the file.

    Returns
    -------
    str
        Lowercase hex SHA-256 digest string.
    """
    hasher = hashlib.sha256()
    chunk_size = 65_536
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


__all__ = [
    "BundleComponent",
    "BundleSovereigntyLevel",
    "BundleManifest",
]
