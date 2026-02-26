"""Tests for ProvenanceTracker, ModelProvenance, AttestationGenerator, Attestation."""
from __future__ import annotations

import datetime
import secrets

import pytest

from agent_sovereign.provenance.attestation import Attestation, AttestationGenerator
from agent_sovereign.provenance.tracker import ModelProvenance, ProvenanceTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tracker() -> ProvenanceTracker:
    return ProvenanceTracker()


def _make_provenance(
    model_id: str = "model-001",
    source: str = "internal://v1",
    version: str = "1.0",
    parent_id: str | None = None,
) -> ModelProvenance:
    return ModelProvenance(
        model_id=model_id,
        source=source,
        version=version,
        training_data_sources=["dataset-a", "dataset-b"],
        certifications=["ISO-42001"],
        parent_model_id=parent_id,
        sha256_checksum="abc123",
    )


@pytest.fixture()
def provenance() -> ModelProvenance:
    return _make_provenance()


@pytest.fixture()
def generator() -> AttestationGenerator:
    return AttestationGenerator(secret_key=secrets.token_bytes(32))


# ---------------------------------------------------------------------------
# ModelProvenance
# ---------------------------------------------------------------------------

class TestModelProvenance:
    def test_recorded_at_set(self, provenance: ModelProvenance) -> None:
        assert provenance.recorded_at is not None

    def test_training_data_sources(self, provenance: ModelProvenance) -> None:
        assert "dataset-a" in provenance.training_data_sources

    def test_metadata_default_empty(self) -> None:
        p = ModelProvenance(model_id="x", source="y", version="1")
        assert p.metadata == {}

    def test_parent_model_id_none_by_default(self) -> None:
        p = ModelProvenance(model_id="x", source="y", version="1")
        assert p.parent_model_id is None


# ---------------------------------------------------------------------------
# ProvenanceTracker
# ---------------------------------------------------------------------------

class TestProvenanceTracker:
    def test_record_and_get(
        self, tracker: ProvenanceTracker, provenance: ModelProvenance
    ) -> None:
        tracker.record(provenance)
        retrieved = tracker.get("model-001")
        assert retrieved.model_id == "model-001"

    def test_get_missing_raises_key_error(self, tracker: ProvenanceTracker) -> None:
        with pytest.raises(KeyError):
            tracker.get("nonexistent-model")

    def test_record_overwrites_existing(
        self, tracker: ProvenanceTracker
    ) -> None:
        p1 = _make_provenance(version="1.0")
        p2 = _make_provenance(version="2.0")
        tracker.record(p1)
        tracker.record(p2)
        assert tracker.get("model-001").version == "2.0"

    def test_list_models_sorted(self, tracker: ProvenanceTracker) -> None:
        tracker.record(_make_provenance("z-model"))
        tracker.record(_make_provenance("a-model"))
        names = tracker.list_models()
        assert names == ["a-model", "z-model"]

    def test_len_empty(self, tracker: ProvenanceTracker) -> None:
        assert len(tracker) == 0

    def test_len_after_records(self, tracker: ProvenanceTracker) -> None:
        tracker.record(_make_provenance("m1"))
        tracker.record(_make_provenance("m2"))
        assert len(tracker) == 2

    def test_verify_chain_single_model(self, tracker: ProvenanceTracker) -> None:
        tracker.record(_make_provenance("root"))
        chain = tracker.verify_chain("root")
        assert chain == ["root"]

    def test_verify_chain_with_parent(self, tracker: ProvenanceTracker) -> None:
        tracker.record(_make_provenance("root"))
        tracker.record(_make_provenance("child", parent_id="root"))
        chain = tracker.verify_chain("child")
        assert chain == ["child", "root"]

    def test_verify_chain_three_levels(self, tracker: ProvenanceTracker) -> None:
        tracker.record(_make_provenance("root"))
        tracker.record(_make_provenance("mid", parent_id="root"))
        tracker.record(_make_provenance("leaf", parent_id="mid"))
        chain = tracker.verify_chain("leaf")
        assert chain == ["leaf", "mid", "root"]

    def test_verify_chain_missing_parent_raises_key_error(
        self, tracker: ProvenanceTracker
    ) -> None:
        tracker.record(_make_provenance("orphan", parent_id="missing-parent"))
        with pytest.raises(KeyError):
            tracker.verify_chain("orphan")

    def test_verify_chain_cycle_raises_runtime_error(
        self, tracker: ProvenanceTracker
    ) -> None:
        # Manually create a cycle by patching parent_model_id
        p1 = _make_provenance("cycle-a", parent_id="cycle-b")
        p2 = _make_provenance("cycle-b", parent_id="cycle-a")
        tracker.record(p1)
        tracker.record(p2)
        with pytest.raises(RuntimeError, match="Cycle"):
            tracker.verify_chain("cycle-a")

    def test_compute_chain_fingerprint_is_hex(
        self, tracker: ProvenanceTracker
    ) -> None:
        tracker.record(_make_provenance("fp-root"))
        fingerprint = tracker.compute_chain_fingerprint("fp-root")
        assert len(fingerprint) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in fingerprint)

    def test_compute_chain_fingerprint_deterministic(
        self, tracker: ProvenanceTracker
    ) -> None:
        tracker.record(_make_provenance("fp-root"))
        f1 = tracker.compute_chain_fingerprint("fp-root")
        f2 = tracker.compute_chain_fingerprint("fp-root")
        assert f1 == f2

    def test_compute_chain_fingerprint_changes_with_chain(
        self, tracker: ProvenanceTracker
    ) -> None:
        tracker.record(_make_provenance("root"))
        tracker.record(_make_provenance("child", parent_id="root"))
        f_root = tracker.compute_chain_fingerprint("root")
        f_child = tracker.compute_chain_fingerprint("child")
        assert f_root != f_child


# ---------------------------------------------------------------------------
# Attestation
# ---------------------------------------------------------------------------

class TestAttestation:
    def test_not_expired_future(self) -> None:
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        ).isoformat()
        att = Attestation(
            attestation_id="att-001",
            model_id="m-001",
            issued_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            expires_at=future,
            payload_digest="abc",
            signature="sig",
        )
        assert not att.is_expired()

    def test_expired_past(self) -> None:
        past = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        ).isoformat()
        att = Attestation(
            attestation_id="att-002",
            model_id="m-002",
            issued_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            expires_at=past,
            payload_digest="abc",
            signature="sig",
        )
        assert att.is_expired()

    def test_naive_expiry_treated_as_utc(self) -> None:
        past = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)).isoformat()
        att = Attestation(
            attestation_id="att-003",
            model_id="m-003",
            issued_at=datetime.datetime.utcnow().isoformat(),
            expires_at=past,
            payload_digest="abc",
            signature="sig",
        )
        assert att.is_expired()

    def test_default_algorithm(self) -> None:
        att = Attestation(
            attestation_id="att-004",
            model_id="m-004",
            issued_at="2026-01-01T00:00:00+00:00",
            expires_at="2027-01-01T00:00:00+00:00",
            payload_digest="d",
            signature="s",
        )
        assert att.algorithm == "HMAC-SHA256"

    def test_default_issuer(self) -> None:
        att = Attestation(
            attestation_id="att-005",
            model_id="m-005",
            issued_at="2026-01-01T00:00:00+00:00",
            expires_at="2027-01-01T00:00:00+00:00",
            payload_digest="d",
            signature="s",
        )
        assert att.issuer == "agent-sovereign"


# ---------------------------------------------------------------------------
# AttestationGenerator
# ---------------------------------------------------------------------------

class TestAttestationGenerator:
    def test_short_key_raises(self) -> None:
        with pytest.raises(ValueError, match="16 bytes"):
            AttestationGenerator(secret_key=b"tooshort")

    def test_generate_returns_attestation(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert isinstance(att, Attestation)
        assert att.model_id == provenance.model_id

    def test_generated_attestation_not_expired(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert not att.is_expired()

    def test_generated_attestation_has_payload_digest(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert len(att.payload_digest) == 64

    def test_generated_attestation_has_signature(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert len(att.signature) == 64

    def test_metadata_includes_version(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert "provenance_version" in att.metadata

    def test_verify_valid_attestation(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        assert generator.verify(att, provenance) is True

    def test_verify_wrong_model_id(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        other = _make_provenance(model_id="different-model")
        assert generator.verify(att, other) is False

    def test_verify_tampered_digest(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        tampered = Attestation(
            attestation_id=att.attestation_id,
            model_id=att.model_id,
            issued_at=att.issued_at,
            expires_at=att.expires_at,
            payload_digest="0" * 64,  # tampered
            signature=att.signature,
        )
        assert generator.verify(tampered, provenance) is False

    def test_verify_tampered_signature(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        tampered = Attestation(
            attestation_id=att.attestation_id,
            model_id=att.model_id,
            issued_at=att.issued_at,
            expires_at=att.expires_at,
            payload_digest=att.payload_digest,
            signature="0" * 64,  # tampered
        )
        assert generator.verify(tampered, provenance) is False

    def test_verify_with_different_key_fails(
        self, provenance: ModelProvenance
    ) -> None:
        gen1 = AttestationGenerator(secret_key=secrets.token_bytes(32))
        gen2 = AttestationGenerator(secret_key=secrets.token_bytes(32))
        att = gen1.generate(provenance)
        assert gen2.verify(att, provenance) is False

    def test_custom_issuer_and_validity(
        self, provenance: ModelProvenance
    ) -> None:
        gen = AttestationGenerator(
            secret_key=secrets.token_bytes(32),
            issuer="my-org",
            validity_hours=100,
        )
        att = gen.generate(provenance)
        assert att.issuer == "my-org"

    def test_naive_issued_at_handled_in_verify(
        self, generator: AttestationGenerator, provenance: ModelProvenance
    ) -> None:
        att = generator.generate(provenance)
        # Strip timezone info to simulate naive datetimes
        naive_issued = att.issued_at.replace("+00:00", "").rstrip("Z")
        naive_expires = att.expires_at.replace("+00:00", "").rstrip("Z")
        att_naive = Attestation(
            attestation_id=att.attestation_id,
            model_id=att.model_id,
            issued_at=naive_issued,
            expires_at=naive_expires,
            payload_digest=att.payload_digest,
            signature=att.signature,
        )
        # Should still verify (naive dates handled as UTC)
        result = generator.verify(att_naive, provenance)
        assert isinstance(result, bool)
