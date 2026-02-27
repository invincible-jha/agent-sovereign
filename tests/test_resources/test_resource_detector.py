"""Tests for agent_sovereign.resources.resource_detector."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_sovereign.resources.resource_detector import (
    BatchSizeRecommendation,
    ModelSizeRecommendation,
    ResourceDetector,
    ResourceProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def detector() -> ResourceDetector:
    return ResourceDetector()


# ---------------------------------------------------------------------------
# Enum completeness
# ---------------------------------------------------------------------------


class TestEnums:
    def test_model_size_has_five_tiers(self) -> None:
        tiers = list(ModelSizeRecommendation)
        assert len(tiers) == 5

    def test_batch_size_has_four_tiers(self) -> None:
        tiers = list(BatchSizeRecommendation)
        assert len(tiers) == 4

    def test_model_size_values(self) -> None:
        assert ModelSizeRecommendation.NANO.value == "nano"
        assert ModelSizeRecommendation.XLARGE.value == "xlarge"

    def test_batch_size_values(self) -> None:
        assert BatchSizeRecommendation.SINGLE.value == "single"
        assert BatchSizeRecommendation.LARGE.value == "large"


# ---------------------------------------------------------------------------
# Model size recommendation
# ---------------------------------------------------------------------------


class TestModelSizeRecommendation:
    def test_gpu_with_large_vram_is_xlarge(self) -> None:
        rec = ResourceDetector.recommend_model_size(
            ram_total_mb=32_000, has_gpu=True, gpu_vram_mb=24_000
        )
        assert rec == ModelSizeRecommendation.XLARGE

    def test_gpu_small_vram_is_large(self) -> None:
        rec = ResourceDetector.recommend_model_size(
            ram_total_mb=16_000, has_gpu=True, gpu_vram_mb=4_000
        )
        assert rec == ModelSizeRecommendation.LARGE

    def test_gpu_no_vram_info_is_large(self) -> None:
        rec = ResourceDetector.recommend_model_size(
            ram_total_mb=8_000, has_gpu=True, gpu_vram_mb=None
        )
        assert rec == ModelSizeRecommendation.LARGE

    def test_64gb_ram_no_gpu_is_xlarge(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=64_000)
        assert rec == ModelSizeRecommendation.XLARGE

    def test_16gb_ram_is_large(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=16_000)
        assert rec == ModelSizeRecommendation.LARGE

    def test_4gb_ram_is_medium(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=4_000)
        assert rec == ModelSizeRecommendation.MEDIUM

    def test_1gb_ram_is_small(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=1_000)
        assert rec == ModelSizeRecommendation.SMALL

    def test_512mb_ram_is_nano(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=512)
        assert rec == ModelSizeRecommendation.NANO

    def test_boundary_just_below_medium(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=3_999)
        assert rec == ModelSizeRecommendation.SMALL

    def test_boundary_just_below_large(self) -> None:
        rec = ResourceDetector.recommend_model_size(ram_total_mb=15_999)
        assert rec == ModelSizeRecommendation.MEDIUM


# ---------------------------------------------------------------------------
# Batch size recommendation
# ---------------------------------------------------------------------------


class TestBatchSizeRecommendation:
    def test_gpu_is_large(self) -> None:
        rec = ResourceDetector.recommend_batch_size(
            cpu_cores=4, ram_available_mb=4_000, has_gpu=True
        )
        assert rec == BatchSizeRecommendation.LARGE

    def test_8_cores_8gb_available_is_medium(self) -> None:
        rec = ResourceDetector.recommend_batch_size(
            cpu_cores=8, ram_available_mb=8_000, has_gpu=False
        )
        assert rec == BatchSizeRecommendation.MEDIUM

    def test_4_cores_2gb_is_small(self) -> None:
        rec = ResourceDetector.recommend_batch_size(
            cpu_cores=4, ram_available_mb=2_000, has_gpu=False
        )
        assert rec == BatchSizeRecommendation.SMALL

    def test_2_cores_1gb_is_single(self) -> None:
        rec = ResourceDetector.recommend_batch_size(
            cpu_cores=2, ram_available_mb=1_000, has_gpu=False
        )
        assert rec == BatchSizeRecommendation.SINGLE

    def test_8_cores_but_low_ram_is_small(self) -> None:
        rec = ResourceDetector.recommend_batch_size(
            cpu_cores=8, ram_available_mb=1_000, has_gpu=False
        )
        assert rec == BatchSizeRecommendation.SINGLE


# ---------------------------------------------------------------------------
# Full detection
# ---------------------------------------------------------------------------


class TestResourceDetector:
    def test_detect_returns_profile(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert isinstance(profile, ResourceProfile)

    def test_profile_is_frozen(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        with pytest.raises((AttributeError, TypeError)):
            profile.cpu_cores_logical = 999  # type: ignore[misc]

    def test_cpu_cores_positive(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert profile.cpu_cores_logical >= 1

    def test_os_name_non_empty(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert len(profile.os_name) > 0

    def test_architecture_non_empty(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert len(profile.architecture) > 0

    def test_model_recommendation_valid_enum(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert isinstance(profile.model_recommendation, ModelSizeRecommendation)

    def test_batch_recommendation_valid_enum(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert isinstance(profile.batch_recommendation, BatchSizeRecommendation)

    def test_ram_total_non_negative(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert profile.ram_total_mb >= 0

    def test_ram_available_non_negative(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert profile.ram_available_mb >= 0

    def test_has_gpu_is_bool(self, detector: ResourceDetector) -> None:
        profile = detector.detect()
        assert isinstance(profile.has_gpu, bool)

    def test_gpu_vram_none_when_no_gpu(self, detector: ResourceDetector) -> None:
        with patch.object(
            ResourceDetector,
            "_detect_gpu",
            return_value=(False, None, None),
        ):
            with patch.object(
                ResourceDetector,
                "_detect_ram",
                return_value=(8_000, 4_000),
            ):
                profile = detector.detect()
        if not profile.has_gpu:
            assert profile.gpu_vram_mb is None

    def test_simulated_high_memory_system(self, detector: ResourceDetector) -> None:
        with patch.object(
            ResourceDetector, "_detect_ram", return_value=(128_000, 64_000)
        ):
            with patch.object(
                ResourceDetector, "_detect_gpu", return_value=(True, "H100", 80_000)
            ):
                profile = detector.detect()
        assert profile.model_recommendation == ModelSizeRecommendation.XLARGE
        assert profile.batch_recommendation == BatchSizeRecommendation.LARGE

    def test_simulated_embedded_system(self, detector: ResourceDetector) -> None:
        with patch.object(
            ResourceDetector, "_detect_cpu_logical", return_value=1
        ):
            with patch.object(
                ResourceDetector, "_detect_ram", return_value=(512, 256)
            ):
                with patch.object(
                    ResourceDetector, "_detect_gpu", return_value=(False, None, None)
                ):
                    profile = detector.detect()
        assert profile.model_recommendation == ModelSizeRecommendation.NANO
        assert profile.batch_recommendation == BatchSizeRecommendation.SINGLE
