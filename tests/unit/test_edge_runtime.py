"""Tests for EdgeRuntime, EdgeConfig, QuantizationLevel."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_sovereign.edge.runtime import (
    EdgeConfig,
    EdgeRuntime,
    PerformanceEstimate,
    QuantizationLevel,
    ResourceValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(
    max_memory_mb: int = 8192,
    max_cpu_percent: float = 80.0,
    quantization: QuantizationLevel = QuantizationLevel.NONE,
    offline_capable: bool = False,
    max_concurrent: int = 1,
    model_cache_dir: str = "/tmp/models",
    gpu_memory_mb: int = 0,
) -> EdgeConfig:
    return EdgeConfig(
        max_memory_mb=max_memory_mb,
        max_cpu_percent=max_cpu_percent,
        model_quantization=quantization,
        offline_capable=offline_capable,
        max_concurrent_requests=max_concurrent,
        model_cache_dir=model_cache_dir,
        gpu_memory_mb=gpu_memory_mb,
    )


@pytest.fixture()
def default_config() -> EdgeConfig:
    return _make_config()


@pytest.fixture()
def runtime(default_config: EdgeConfig) -> EdgeRuntime:
    return EdgeRuntime(default_config)


# ---------------------------------------------------------------------------
# EdgeConfig defaults
# ---------------------------------------------------------------------------

class TestEdgeConfigDefaults:
    def test_quantization_default(self) -> None:
        config = EdgeConfig(max_memory_mb=1024, max_cpu_percent=50.0)
        assert config.model_quantization == QuantizationLevel.NONE

    def test_offline_default_false(self) -> None:
        config = EdgeConfig(max_memory_mb=1024, max_cpu_percent=50.0)
        assert config.offline_capable is False

    def test_gpu_default_zero(self) -> None:
        config = EdgeConfig(max_memory_mb=1024, max_cpu_percent=50.0)
        assert config.gpu_memory_mb == 0

    def test_heartbeat_default(self) -> None:
        config = EdgeConfig(max_memory_mb=1024, max_cpu_percent=50.0)
        assert config.heartbeat_interval_seconds == 60


# ---------------------------------------------------------------------------
# EdgeRuntime.config property
# ---------------------------------------------------------------------------

class TestEdgeRuntimeConfig:
    def test_config_accessible(self, runtime: EdgeRuntime, default_config: EdgeConfig) -> None:
        assert runtime.config is default_config


# ---------------------------------------------------------------------------
# EdgeRuntime.validate_resources
# ---------------------------------------------------------------------------

class TestValidateResources:
    def test_valid_when_enough_memory(self, runtime: EdgeRuntime) -> None:
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            result = runtime.validate_resources()
        assert result.is_valid is True
        assert result.errors == []

    def test_error_when_insufficient_memory(self) -> None:
        config = _make_config(max_memory_mb=16000)
        rt = EdgeRuntime(config)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=4000):
            result = rt.validate_resources()
        assert not result.is_valid
        assert any("Insufficient memory" in e for e in result.errors)

    def test_warning_when_tight_memory(self) -> None:
        config = _make_config(max_memory_mb=8000)
        rt = EdgeRuntime(config)
        # 1.1x max_memory_mb means between 1.0x and 1.2x → tight
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=8500):
            result = rt.validate_resources()
        assert any("tight" in w.lower() for w in result.warnings)

    def test_error_on_invalid_cpu_percent(self) -> None:
        config = _make_config(max_cpu_percent=150.0)
        rt = EdgeRuntime(config)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            result = rt.validate_resources()
        assert not result.is_valid
        assert any("max_cpu_percent" in e for e in result.errors)

    def test_error_on_zero_cpu_percent(self) -> None:
        config = _make_config(max_cpu_percent=0.0)
        rt = EdgeRuntime(config)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            result = rt.validate_resources()
        assert not result.is_valid

    def test_warning_single_cpu_high_concurrency(self) -> None:
        config = _make_config(max_concurrent=4)
        rt = EdgeRuntime(config)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            with patch("os.cpu_count", return_value=1):
                result = rt.validate_resources()
        assert any("Single logical CPU" in w for w in result.warnings)

    def test_error_offline_without_cache_dir(self) -> None:
        config = _make_config(offline_capable=True, model_cache_dir="")
        rt = EdgeRuntime(config)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            result = rt.validate_resources()
        assert not result.is_valid
        assert any("model_cache_dir" in e for e in result.errors)

    def test_result_has_memory_and_cpu(self, runtime: EdgeRuntime) -> None:
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            result = runtime.validate_resources()
        assert result.available_memory_mb == 16000
        assert result.available_cpu_count >= 1


# ---------------------------------------------------------------------------
# EdgeRuntime._detect_available_memory_mb
# ---------------------------------------------------------------------------

class TestDetectMemory:
    def test_psutil_used_when_available(self) -> None:
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value.available = 8 * 1024 * 1024 * 1024
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = EdgeRuntime._detect_available_memory_mb()
        assert result == 8192

    def test_fallback_default_when_no_psutil_no_proc(self) -> None:
        with patch.dict("sys.modules", {"psutil": None}):
            with patch("builtins.open", side_effect=OSError("no proc")):
                result = EdgeRuntime._detect_available_memory_mb()
        assert result == 512

    def test_returns_int(self, runtime: EdgeRuntime) -> None:
        result = EdgeRuntime._detect_available_memory_mb()
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# EdgeRuntime.estimate_performance
# ---------------------------------------------------------------------------

class TestEstimatePerformance:
    def test_returns_performance_estimate(self, runtime: EdgeRuntime) -> None:
        estimate = runtime.estimate_performance(7.0)
        assert isinstance(estimate, PerformanceEstimate)

    def test_model_too_large_adds_note(self) -> None:
        config = _make_config(max_memory_mb=1024, quantization=QuantizationLevel.NONE)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(70.0)  # 70B model at fp16 >> 1024MB
        assert any("exceeds" in note for note in estimate.notes)
        assert estimate.max_context_tokens == 0

    def test_model_fits_gives_context_tokens(self) -> None:
        config = _make_config(max_memory_mb=32000)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.max_context_tokens > 0

    def test_quantization_speedup_int8(self) -> None:
        config = _make_config(quantization=QuantizationLevel.INT8)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.quantization_speedup_factor == 1.5

    def test_quantization_speedup_int4(self) -> None:
        config = _make_config(quantization=QuantizationLevel.INT4)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.quantization_speedup_factor == 2.2

    def test_quantization_speedup_none(self) -> None:
        config = _make_config(quantization=QuantizationLevel.NONE)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.quantization_speedup_factor == 1.0

    def test_gpu_memory_adds_note(self) -> None:
        config = _make_config(gpu_memory_mb=8000)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert any("GPU" in note for note in estimate.notes)

    def test_gpu_increases_tokens_per_second(self) -> None:
        config_cpu = _make_config(gpu_memory_mb=0)
        config_gpu = _make_config(gpu_memory_mb=8000)
        rt_cpu = EdgeRuntime(config_cpu)
        rt_gpu = EdgeRuntime(config_gpu)
        with patch.object(EdgeRuntime, "_detect_available_memory_mb", return_value=16000):
            est_cpu = rt_cpu.estimate_performance(7.0)
            est_gpu = rt_gpu.estimate_performance(7.0)
        assert est_gpu.tokens_per_second > est_cpu.tokens_per_second

    def test_time_to_first_token_at_least_50ms(self, runtime: EdgeRuntime) -> None:
        estimate = runtime.estimate_performance(7.0)
        assert estimate.time_to_first_token_ms >= 50.0

    def test_gguf_q5_bytes_per_param(self) -> None:
        config = _make_config(max_memory_mb=64000, quantization=QuantizationLevel.GGUF_Q5_K_M)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.max_context_tokens > 0

    def test_gguf_q8_bytes_per_param(self) -> None:
        config = _make_config(max_memory_mb=64000, quantization=QuantizationLevel.GGUF_Q8_0)
        rt = EdgeRuntime(config)
        estimate = rt.estimate_performance(7.0)
        assert estimate.quantization_speedup_factor == 1.3


# Need this import for TestDetectMemory
from unittest.mock import MagicMock
