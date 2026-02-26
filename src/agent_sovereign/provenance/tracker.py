"""Model provenance tracker.

Records, retrieves, and verifies chain-of-custody information for
model artefacts used in sovereign deployments.
"""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field


@dataclass
class ModelProvenance:
    """Provenance record for a deployed model artefact.

    Attributes
    ----------
    model_id:
        Unique identifier for the model (e.g. a URN or content hash).
    source:
        Origin URI or description (e.g. "huggingface://org/model" or
        "internal-registry://models/v2").
    version:
        Version string for the model.
    training_data_sources:
        List of dataset identifiers used in training.
    certifications:
        List of certification or audit identifiers (e.g. "ISO-42001:2023").
    recorded_at:
        ISO-8601 UTC timestamp of when this record was created.
    parent_model_id:
        Optional ID of the parent model (for fine-tuned or derived models).
    sha256_checksum:
        Optional SHA-256 hex digest of the model artefact file.
    metadata:
        Additional key/value pairs attached to this provenance record.
    """

    model_id: str
    source: str
    version: str
    training_data_sources: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    recorded_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    parent_model_id: str | None = None
    sha256_checksum: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class ProvenanceTracker:
    """Records and retrieves model provenance records.

    Maintains an in-memory store of ModelProvenance entries indexed by
    model_id. For production use, back this with a persistent store by
    subclassing and overriding ``_store`` and ``_load``.

    The tracker also supports chain-of-custody verification: given a
    model_id, it walks the parent_model_id chain and confirms that
    every ancestor in the chain has a recorded provenance entry.
    """

    def __init__(self) -> None:
        self._records: dict[str, ModelProvenance] = {}

    def record(self, provenance: ModelProvenance) -> None:
        """Record or update a provenance entry for a model.

        If a record already exists for ``provenance.model_id``, it is
        overwritten with the new entry.

        Parameters
        ----------
        provenance:
            The ModelProvenance record to store.
        """
        self._records[provenance.model_id] = provenance

    def get(self, model_id: str) -> ModelProvenance:
        """Retrieve the provenance record for a model.

        Parameters
        ----------
        model_id:
            The unique model identifier.

        Returns
        -------
        ModelProvenance
            The stored provenance record.

        Raises
        ------
        KeyError
            If no record exists for ``model_id``.
        """
        if model_id not in self._records:
            raise KeyError(
                f"No provenance record found for model_id={model_id!r}. "
                "Ensure record() was called before get()."
            )
        return self._records[model_id]

    def verify_chain(self, model_id: str) -> list[str]:
        """Walk and verify the full provenance chain for a model.

        Starting from ``model_id``, follows parent_model_id links until a
        root (no parent) is reached. Verifies that every ancestor has a
        provenance record.

        Parameters
        ----------
        model_id:
            The leaf model to start verification from.

        Returns
        -------
        list[str]
            Ordered list of model IDs in the chain from leaf to root.
            Each ID is guaranteed to have a corresponding provenance record.

        Raises
        ------
        KeyError
            If any link in the chain references an ID with no provenance record.
        RuntimeError
            If a cycle is detected in the parent chain.
        """
        chain: list[str] = []
        visited: set[str] = set()
        current_id: str | None = model_id

        while current_id is not None:
            if current_id in visited:
                raise RuntimeError(
                    f"Cycle detected in provenance chain at model_id={current_id!r}. "
                    "Chain so far: " + " -> ".join(chain)
                )
            record = self.get(current_id)  # raises KeyError if missing
            chain.append(current_id)
            visited.add(current_id)
            current_id = record.parent_model_id

        return chain

    def compute_chain_fingerprint(self, model_id: str) -> str:
        """Compute a deterministic fingerprint for the full provenance chain.

        The fingerprint is a SHA-256 digest of the ordered model IDs in the
        chain, useful for detecting chain tampering.

        Parameters
        ----------
        model_id:
            The leaf model whose chain to fingerprint.

        Returns
        -------
        str
            Hex-encoded SHA-256 digest of the joined chain IDs.
        """
        chain = self.verify_chain(model_id)
        raw = "|".join(chain).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def list_models(self) -> list[str]:
        """Return a sorted list of all tracked model IDs.

        Returns
        -------
        list[str]
            All model identifiers in the store.
        """
        return sorted(self._records)

    def __len__(self) -> int:
        """Return the number of provenance records in the store."""
        return len(self._records)


__all__ = [
    "ModelProvenance",
    "ProvenanceTracker",
]
