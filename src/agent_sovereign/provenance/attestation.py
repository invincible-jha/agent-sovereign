"""HMAC-based attestation for model provenance records.

Generates and verifies cryptographic attestations that bind a provenance
record to a signing key, providing tamper evidence for the record.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field

from agent_sovereign.provenance.tracker import ModelProvenance


@dataclass
class Attestation:
    """A cryptographic attestation for a model provenance record.

    Attributes
    ----------
    attestation_id:
        Unique identifier for this attestation.
    model_id:
        The model this attestation covers.
    issued_at:
        ISO-8601 UTC timestamp of attestation issuance.
    expires_at:
        ISO-8601 UTC timestamp after which this attestation should be
        considered expired (does not enforce revocation automatically).
    payload_digest:
        SHA-256 hex digest of the canonical JSON payload that was signed.
    signature:
        HMAC-SHA256 hex digest produced by signing the payload_digest
        with the issuer's secret key.
    algorithm:
        The signing algorithm identifier (always "HMAC-SHA256" for built-in).
    issuer:
        Identifier for the entity that issued this attestation.
    metadata:
        Additional key/value pairs embedded in the attestation.
    """

    attestation_id: str
    model_id: str
    issued_at: str
    expires_at: str
    payload_digest: str
    signature: str
    algorithm: str = "HMAC-SHA256"
    issuer: str = "agent-sovereign"
    metadata: dict[str, str] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Return True if the attestation's expiry time has passed.

        Returns
        -------
        bool
            True if ``expires_at`` is in the past relative to UTC now.
        """
        expiry = datetime.datetime.fromisoformat(self.expires_at)
        now = datetime.datetime.now(datetime.timezone.utc)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
        return now > expiry


class AttestationGenerator:
    """Generates and verifies HMAC-SHA256 attestations for provenance records.

    Parameters
    ----------
    secret_key:
        The HMAC signing key as bytes. Must be kept secret. At minimum
        16 bytes recommended; 32+ bytes preferred.
    issuer:
        Human-readable identifier for the issuing entity (embedded in
        the generated attestation).
    validity_hours:
        How many hours the generated attestation remains valid.
        Default is 8760 (one year).
    """

    def __init__(
        self,
        secret_key: bytes,
        issuer: str = "agent-sovereign",
        validity_hours: int = 8760,
    ) -> None:
        if len(secret_key) < 16:
            raise ValueError(
                "secret_key must be at least 16 bytes. "
                "Use secrets.token_bytes(32) to generate a strong key."
            )
        self._secret_key = secret_key
        self._issuer = issuer
        self._validity_hours = validity_hours

    def generate(self, provenance: ModelProvenance) -> Attestation:
        """Generate an HMAC-SHA256 attestation for a provenance record.

        Builds a canonical JSON payload from the provenance record,
        computes its SHA-256 digest, then signs the digest with HMAC-SHA256.

        Parameters
        ----------
        provenance:
            The ModelProvenance record to attest.

        Returns
        -------
        Attestation
            The signed attestation. Store or transmit this alongside the
            provenance record.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(hours=self._validity_hours)

        attestation_id = secrets.token_hex(16)

        payload = self._build_payload(provenance, attestation_id, now, expires)
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()

        signature = hmac.new(
            key=self._secret_key,
            msg=payload_digest.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return Attestation(
            attestation_id=attestation_id,
            model_id=provenance.model_id,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
            payload_digest=payload_digest,
            signature=signature,
            algorithm="HMAC-SHA256",
            issuer=self._issuer,
            metadata={
                "provenance_version": provenance.version,
                "training_data_count": str(len(provenance.training_data_sources)),
                "certifications": ",".join(provenance.certifications),
            },
        )

    def verify(self, attestation: Attestation, provenance: ModelProvenance) -> bool:
        """Verify that an attestation is valid for a provenance record.

        Recomputes the expected payload digest and HMAC signature, then
        compares them to the stored values using constant-time comparison
        to prevent timing attacks.

        Parameters
        ----------
        attestation:
            The Attestation to verify.
        provenance:
            The ModelProvenance record the attestation was issued for.

        Returns
        -------
        bool
            True if the attestation is cryptographically valid and the
            model_id matches. Does not check expiry — call
            ``attestation.is_expired()`` separately if needed.
        """
        if attestation.model_id != provenance.model_id:
            return False

        issued_at = datetime.datetime.fromisoformat(attestation.issued_at)
        expires_at = datetime.datetime.fromisoformat(attestation.expires_at)
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=datetime.timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)

        payload = self._build_payload(provenance, attestation.attestation_id, issued_at, expires_at)
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_digest = hashlib.sha256(payload_bytes).hexdigest()

        if not hmac.compare_digest(expected_digest, attestation.payload_digest):
            return False

        expected_sig = hmac.new(
            key=self._secret_key,
            msg=expected_digest.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, attestation.signature)

    @staticmethod
    def _build_payload(
        provenance: ModelProvenance,
        attestation_id: str,
        issued_at: datetime.datetime,
        expires_at: datetime.datetime,
    ) -> dict[str, object]:
        """Build the canonical payload dict for signing.

        Parameters
        ----------
        provenance:
            The provenance record to include.
        attestation_id:
            The unique attestation identifier.
        issued_at:
            Issuance timestamp.
        expires_at:
            Expiry timestamp.

        Returns
        -------
        dict[str, object]
            A JSON-serialisable dict with all fields that contribute to
            the signature.
        """
        return {
            "attestation_id": attestation_id,
            "model_id": provenance.model_id,
            "source": provenance.source,
            "version": provenance.version,
            "training_data_sources": sorted(provenance.training_data_sources),
            "certifications": sorted(provenance.certifications),
            "recorded_at": provenance.recorded_at,
            "parent_model_id": provenance.parent_model_id,
            "sha256_checksum": provenance.sha256_checksum,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }


__all__ = [
    "Attestation",
    "AttestationGenerator",
]
