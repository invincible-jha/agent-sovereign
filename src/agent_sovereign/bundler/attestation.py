"""Bundle attestation — build provenance and integrity verification.

Attestations are signed (or signable) records that bind a BundleManifest
to verifiable claims about *how* it was built and *what* it contains.
They provide an audit trail for sovereign deployments.

The signature field is a placeholder for future cryptographic integration
(e.g. Sigstore, DSSE, or custom HMAC).  The current implementation
records all claims as a deterministic JSON payload and stores a SHA-256
digest of that payload as the "signature" until a proper signing key is
configured.

Classes
-------
- AttestationType        Enum of recognised attestation categories.
- Attestation            Frozen dataclass representing a single attestation.
- AttestationGenerator   Generates and verifies attestations for manifests.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import platform
import secrets
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent_sovereign.bundler.manifest import BundleManifest


# ---------------------------------------------------------------------------
# Attestation type enum
# ---------------------------------------------------------------------------


class AttestationType(str, Enum):
    """Classification of what an attestation certifies.

    Values
    ------
    BUILD_PROVENANCE:
        Records *how* and *where* the bundle was built (timestamp,
        Python version, platform, component hashes).
    SECURITY_SCAN:
        Records the result of a dependency or container security scan.
    COMPLIANCE_CHECK:
        Records the result of a sovereignty compliance evaluation.
    INTEGRITY_VERIFICATION:
        Records the result of verifying all component checksums.
    """

    BUILD_PROVENANCE = "build_provenance"
    SECURITY_SCAN = "security_scan"
    COMPLIANCE_CHECK = "compliance_check"
    INTEGRITY_VERIFICATION = "integrity_verification"


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attestation:
    """A signed record certifying a claim about a BundleManifest.

    Attributes
    ----------
    attestation_id:
        Unique identifier for this attestation (random hex string).
    attestation_type:
        Category of claim being made.
    subject:
        The ``bundle_id`` of the BundleManifest this attestation covers.
    issuer:
        Human-readable identifier for the system or person that issued
        the attestation.
    issued_at:
        UTC datetime of attestation issuance.
    claims:
        Structured claim data.  Content depends on ``attestation_type``.
    signature:
        SHA-256 digest of the canonical claim payload, used as a
        placeholder until a proper signing infrastructure is plugged in.
        ``None`` for unsigned attestations.
    """

    attestation_id: str
    attestation_type: AttestationType
    subject: str
    issuer: str
    issued_at: datetime.datetime
    claims: dict[str, object]
    signature: str | None = None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class AttestationGenerator:
    """Generates and verifies attestations for BundleManifest objects.

    Parameters
    ----------
    issuer:
        Label for the issuing entity embedded in every generated
        attestation (e.g. ``"agent-sovereign/bundler"``).
    """

    def __init__(self, issuer: str = "agent-sovereign/bundler") -> None:
        self._issuer = issuer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_build_provenance(self, manifest: BundleManifest) -> Attestation:
        """Generate a BUILD_PROVENANCE attestation for a manifest.

        Records the build timestamp, Python version, OS platform, and
        the SHA-256 checksums of all included components.

        Parameters
        ----------
        manifest:
            The BundleManifest to attest.

        Returns
        -------
        Attestation
            A signed build provenance record.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        claims: dict[str, object] = {
            "bundle_id": manifest.bundle_id,
            "created_at": manifest.created_at.isoformat(),
            "sovereignty_level": manifest.sovereignty_level.value,
            "target_platform": manifest.target_platform,
            "python_version": sys.version,
            "platform": platform.platform(),
            "component_count": len(manifest.components),
            "component_hashes": {
                c.name: c.checksum for c in manifest.components
            },
            "total_size_bytes": manifest.compute_total_size(),
            "metadata": manifest.metadata,
        }

        signature = self._sign_claims(claims)

        return Attestation(
            attestation_id=secrets.token_hex(16),
            attestation_type=AttestationType.BUILD_PROVENANCE,
            subject=manifest.bundle_id,
            issuer=self._issuer,
            issued_at=now,
            claims=claims,
            signature=signature,
        )

    def generate_integrity_attestation(
        self, manifest: BundleManifest, base_path: Path
    ) -> Attestation:
        """Generate an INTEGRITY_VERIFICATION attestation.

        Verifies every component checksum against files on disk and
        records the per-component pass/fail status in the claims.

        Parameters
        ----------
        manifest:
            The BundleManifest to verify.
        base_path:
            Directory under which component paths are resolved.

        Returns
        -------
        Attestation
            An attestation recording the integrity verification results.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        verification_results = manifest.verify_checksums(base_path)
        all_passed = all(valid for _, valid in verification_results)

        claims: dict[str, object] = {
            "bundle_id": manifest.bundle_id,
            "verified_at": now.isoformat(),
            "base_path": str(base_path),
            "all_checksums_valid": all_passed,
            "component_results": {
                name: valid for name, valid in verification_results
            },
            "component_count": len(manifest.components),
            "passed_count": sum(1 for _, v in verification_results if v),
            "failed_count": sum(1 for _, v in verification_results if not v),
        }

        signature = self._sign_claims(claims)

        return Attestation(
            attestation_id=secrets.token_hex(16),
            attestation_type=AttestationType.INTEGRITY_VERIFICATION,
            subject=manifest.bundle_id,
            issuer=self._issuer,
            issued_at=now,
            claims=claims,
            signature=signature,
        )

    def verify_attestation(self, attestation: Attestation) -> bool:
        """Verify the structural integrity of an attestation.

        Recomputes the signature from the stored claims and compares it
        to the stored signature using a constant-time comparison.

        For attestations with ``signature=None`` (unsigned), returns
        ``False`` as they cannot be verified.

        Parameters
        ----------
        attestation:
            The Attestation to verify.

        Returns
        -------
        bool
            ``True`` if the recomputed signature matches the stored one
            and all required fields are present.  ``False`` otherwise.
        """
        if attestation.signature is None:
            return False

        if not attestation.attestation_id:
            return False
        if not attestation.subject:
            return False
        if not attestation.issuer:
            return False

        expected_signature = self._sign_claims(attestation.claims)

        # Constant-time comparison to resist timing attacks
        sig_a = attestation.signature.encode("utf-8")
        sig_b = expected_signature.encode("utf-8")
        if len(sig_a) != len(sig_b):
            return False

        result = 0
        for byte_a, byte_b in zip(sig_a, sig_b):
            result |= byte_a ^ byte_b
        return result == 0

    def export_attestations(
        self,
        attestations: list[Attestation],
        path: Path,
    ) -> None:
        """Write a list of attestations to a JSON file.

        Parameters
        ----------
        attestations:
            Attestations to export.
        path:
            Destination file path.  Parent directories must exist.
        """
        records: list[dict[str, object]] = [
            _attestation_to_dict(att) for att in attestations
        ]
        path.write_text(
            json.dumps(records, indent=2, default=str),
            encoding="utf-8",
        )

    def import_attestations(self, path: Path) -> list[Attestation]:
        """Load attestations from a previously exported JSON file.

        Parameters
        ----------
        path:
            Path to the JSON file produced by :meth:`export_attestations`.

        Returns
        -------
        list[Attestation]
            Reconstructed Attestation objects.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        json.JSONDecodeError
            If the file content is not valid JSON.
        """
        if not path.exists():
            raise FileNotFoundError(
                f"Attestation file not found: {path}"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [_attestation_from_dict(record) for record in raw]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sign_claims(claims: dict[str, object]) -> str:
        """Compute a deterministic SHA-256 signature for a claims dict.

        Serialises the claims to canonical JSON (sorted keys, no extra
        whitespace) and returns the hex digest.

        This is an extension point: replace this method to integrate
        with Sigstore, HMAC, or another signing scheme.

        Parameters
        ----------
        claims:
            The claims dictionary to sign.

        Returns
        -------
        str
            Lowercase hex SHA-256 digest of the canonical payload.
        """
        payload = json.dumps(claims, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _attestation_to_dict(attestation: Attestation) -> dict[str, object]:
    """Convert an Attestation dataclass to a JSON-serialisable dict."""
    return {
        "attestation_id": attestation.attestation_id,
        "attestation_type": attestation.attestation_type.value,
        "subject": attestation.subject,
        "issuer": attestation.issuer,
        "issued_at": attestation.issued_at.isoformat(),
        "claims": attestation.claims,
        "signature": attestation.signature,
    }


def _attestation_from_dict(record: dict[str, object]) -> Attestation:
    """Reconstruct an Attestation from a dict (e.g. loaded from JSON)."""
    issued_at_raw = record["issued_at"]
    if isinstance(issued_at_raw, str):
        issued_at = datetime.datetime.fromisoformat(issued_at_raw)
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=datetime.timezone.utc)
    else:
        issued_at = issued_at_raw

    return Attestation(
        attestation_id=record["attestation_id"],
        attestation_type=AttestationType(record["attestation_type"]),
        subject=record["subject"],
        issuer=record["issuer"],
        issued_at=issued_at,
        claims=record["claims"],
        signature=record.get("signature"),
    )


__all__ = [
    "Attestation",
    "AttestationGenerator",
    "AttestationType",
]
