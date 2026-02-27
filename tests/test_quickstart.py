"""Test that the 3-line quickstart API works for agent-sovereign."""
from __future__ import annotations


def test_quickstart_import() -> None:
    from agent_sovereign import Bundler

    bundler = Bundler()
    assert bundler is not None


def test_quickstart_bundle_basic() -> None:
    from agent_sovereign import Bundler

    bundler = Bundler()
    bundle = bundler.bundle({"agent_id": "demo-agent", "model": "gpt-4o"})
    assert bundle is not None


def test_quickstart_bundle_has_sovereignty_level() -> None:
    from agent_sovereign import Bundler
    from agent_sovereign.classifier.levels import SovereigntyLevel

    bundler = Bundler()
    bundle = bundler.bundle({"agent_id": "cloud-agent", "data_types": ["public"]})
    assert isinstance(bundle.sovereignty_level, SovereigntyLevel)


def test_quickstart_bundle_phi_data() -> None:
    from agent_sovereign import Bundler
    from agent_sovereign.classifier.levels import SovereigntyLevel

    bundler = Bundler()
    bundle = bundler.bundle({
        "agent_id": "hipaa-agent",
        "data_types": ["phi"],
        "regulations": ["HIPAA"],
    })
    # PHI data should require higher sovereignty
    assert bundle.sovereignty_level.value >= SovereigntyLevel.L3_HYBRID.value


def test_quickstart_bundle_result_repr() -> None:
    from agent_sovereign import Bundler

    bundler = Bundler()
    bundle = bundler.bundle({"agent_id": "repr-agent"})
    text = repr(bundle)
    assert "BundleResult" in text


def test_quickstart_assessor_accessible() -> None:
    from agent_sovereign import Bundler
    from agent_sovereign.classifier.assessor import SovereigntyAssessor

    bundler = Bundler()
    assert isinstance(bundler.assessor, SovereigntyAssessor)
