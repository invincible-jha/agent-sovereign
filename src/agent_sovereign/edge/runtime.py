"""Edge runtime configuration and resource validation.

Defines EdgeConfig and EdgeRuntime, which validate hardware resources and
estimate inference performance for edge-deployed agent bundles.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class QuantizationLevel(str, Enum):
    """Supported model quantization levels for edge inference."""

    NONE = "none"
    INT8 = "int8"
    INT4 = "int4"
    GGUF_Q4_K_M = "gguf_q4_k_m"
    GGUF_Q5_K_M = "gguf_q5_k_m"
    GGUF_Q8_0 = "gguf_q8_0"


@dataclass
class EdgeConfig:
    """Configuration for an edge runtime environment.

    Attributes
    ----------
    max_memory_mb:
        Maximum RAM available for model and inference (MiB).
    max_cpu_percent:
        Maximum CPU utilisation percentage (0–100) allowed.
    model_quantization:
        Quantization level to apply to loaded models.
    offline_capable:
        Whether this edge node can operate without network connectivity.
    max_concurrent_requests:
        Maximum number of simultaneous inference requests.
    model_cache_dir:
        Path to the directory where model weights are cached locally.
    gpu_memory_mb:
        GPU memory available in MiB (0 if no GPU present).
    enable_model_caching:
        Whether to cache model activations across requests.
    heartbeat_interval_seconds:
        How often the edge node should send a heartbeat to the sync endpoint.
    """

    max_memory_mb: int
    max_cpu_percent: float
    model_quantization: QuantizationLevel = QuantizationLevel.NONE
    offline_capable: bool = False
    max_concurrent_requests: int = 1
    model_cache_dir: str = "/var/cache/agent-sovereign/models"
    gpu_memory_mb: int = 0
    enable_model_caching: bool = True
    heartbeat_interval_seconds: int = 60


@dataclass
class ResourceValidationResult:
    """Result of a resource validation check.

    Attributes
    ----------
    is_valid:
        True if all resource requirements are met.
    warnings:
        Non-fatal issues detected during validation.
    errors:
        Fatal issues that prevent the runtime from operating correctly.
    available_memory_mb:
        Detected available system memory in MiB.
    available_cpu_count:
        Detected logical CPU count.
    """

    is_valid: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    available_memory_mb: int = 0
    available_cpu_count: int = 0


@dataclass
class PerformanceEstimate:
    """Estimated inference performance for an edge configuration.

    Attributes
    ----------
    tokens_per_second:
        Estimated token generation rate.
    time_to_first_token_ms:
        Estimated latency to the first output token in milliseconds.
    max_context_tokens:
        Estimated maximum context length supported given memory constraints.
    quantization_speedup_factor:
        Estimated throughput multiplier from quantization (1.0 = no speedup).
    notes:
        Explanatory notes about the estimate.
    """

    tokens_per_second: float
    time_to_first_token_ms: float
    max_context_tokens: int
    quantization_speedup_factor: float
    notes: list[str] = field(default_factory=list)


# Quantization speedup multipliers (approximate, hardware-agnostic)
_QUANTIZATION_SPEEDUP: dict[QuantizationLevel, float] = {
    QuantizationLevel.NONE: 1.0,
    QuantizationLevel.INT8: 1.5,
    QuantizationLevel.INT4: 2.2,
    QuantizationLevel.GGUF_Q4_K_M: 2.0,
    QuantizationLevel.GGUF_Q5_K_M: 1.7,
    QuantizationLevel.GGUF_Q8_0: 1.3,
}

# Memory per context token estimate (bytes at fp16 precision)
_BYTES_PER_TOKEN_FP16 = 2048


class EdgeRuntime:
    """Manages edge deployment runtime configuration and resource checks.

    Parameters
    ----------
    config:
        The EdgeConfig describing resource limits and runtime preferences.
    """

    def __init__(self, config: EdgeConfig) -> None:
        self._config = config

    @property
    def config(self) -> EdgeConfig:
        """Return the active EdgeConfig."""
        return self._config

    def validate_resources(self) -> ResourceValidationResult:
        """Validate that system resources satisfy the EdgeConfig requirements.

        Reads available memory and CPU from the OS (best-effort; falls back
        to conservative defaults if OS APIs are unavailable). Compares against
        limits specified in EdgeConfig.

        Returns
        -------
        ResourceValidationResult
            Validation outcome with any errors or warnings.
        """
        warnings: list[str] = []
        errors: list[str] = []

        # Detect available memory
        available_memory_mb = self._detect_available_memory_mb()
        cpu_count = os.cpu_count() or 1

        # Memory check
        if available_memory_mb < self._config.max_memory_mb:
            errors.append(
                f"Insufficient memory: EdgeConfig requires {self._config.max_memory_mb} MiB, "
                f"but only {available_memory_mb} MiB is available."
            )
        elif available_memory_mb < self._config.max_memory_mb * 1.2:
            warnings.append(
                f"Memory is tight: {available_memory_mb} MiB available vs "
                f"{self._config.max_memory_mb} MiB configured. "
                "Consider reducing max_memory_mb or adding RAM."
            )

        # CPU check
        if self._config.max_cpu_percent <= 0 or self._config.max_cpu_percent > 100:
            errors.append(
                f"max_cpu_percent must be between 0 and 100, "
                f"got {self._config.max_cpu_percent}."
            )

        if cpu_count == 1 and self._config.max_concurrent_requests > 1:
            warnings.append(
                "Single logical CPU detected. max_concurrent_requests > 1 may "
                "cause significant contention."
            )

        # Offline check
        if self._config.offline_capable and not self._config.model_cache_dir:
            errors.append(
                "offline_capable is True but model_cache_dir is not set. "
                "Models cannot be loaded without a local cache."
            )

        is_valid = len(errors) == 0

        return ResourceValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            available_memory_mb=available_memory_mb,
            available_cpu_count=cpu_count,
        )

    def estimate_performance(self, model_parameter_count_billions: float) -> PerformanceEstimate:
        """Estimate inference performance for a model of the given size.

        Uses heuristic formulas based on memory, quantization level, and
        model size. These are coarse estimates for capacity planning only.

        Parameters
        ----------
        model_parameter_count_billions:
            The size of the model in billions of parameters
            (e.g. 7.0 for a 7B model).

        Returns
        -------
        PerformanceEstimate
            Estimated performance metrics for this runtime configuration.
        """
        notes: list[str] = []
        speedup = _QUANTIZATION_SPEEDUP.get(self._config.model_quantization, 1.0)

        # Bytes required for model weights at given quantization
        bytes_per_param: float
        if self._config.model_quantization in (
            QuantizationLevel.NONE,
        ):
            bytes_per_param = 2.0  # fp16
        elif self._config.model_quantization in (
            QuantizationLevel.INT8,
            QuantizationLevel.GGUF_Q8_0,
        ):
            bytes_per_param = 1.0
        elif self._config.model_quantization in (
            QuantizationLevel.GGUF_Q5_K_M,
        ):
            bytes_per_param = 0.625
        else:  # INT4 / GGUF_Q4_K_M
            bytes_per_param = 0.5

        model_size_mb = (model_parameter_count_billions * 1e9 * bytes_per_param) / (1024 * 1024)

        if model_size_mb > self._config.max_memory_mb:
            notes.append(
                f"Model size ({model_size_mb:.0f} MiB at {self._config.model_quantization.value}) "
                f"exceeds max_memory_mb ({self._config.max_memory_mb}). "
                "Consider increasing max_memory_mb or using stronger quantization."
            )
            max_context_tokens = 0
        else:
            remaining_mb = self._config.max_memory_mb - model_size_mb
            max_context_tokens = max(
                0,
                int((remaining_mb * 1024 * 1024) / _BYTES_PER_TOKEN_FP16),
            )

        # Heuristic: baseline ~10 tok/s per CPU core at fp16 for a 7B model
        cpu_count = os.cpu_count() or 1
        cpu_factor = min(cpu_count, 8)  # diminishing returns beyond 8 cores
        baseline_tokens_per_second = (cpu_factor * 10.0) / max(
            1.0, model_parameter_count_billions / 7.0
        )
        tokens_per_second = baseline_tokens_per_second * speedup

        if self._config.gpu_memory_mb > 0:
            # GPU acceleration: rough 10x over CPU
            gpu_factor = min(self._config.gpu_memory_mb / max(1.0, model_size_mb), 10.0)
            tokens_per_second *= max(1.0, gpu_factor * 3.0)
            notes.append(
                f"GPU memory ({self._config.gpu_memory_mb} MiB) detected; "
                "applying GPU acceleration factor."
            )

        # Time to first token grows with model size and shrinks with quantization
        time_to_first_token_ms = max(
            50.0,
            (model_parameter_count_billions * 100.0) / speedup,
        )

        return PerformanceEstimate(
            tokens_per_second=round(tokens_per_second, 2),
            time_to_first_token_ms=round(time_to_first_token_ms, 1),
            max_context_tokens=max_context_tokens,
            quantization_speedup_factor=speedup,
            notes=notes,
        )

    @staticmethod
    def _detect_available_memory_mb() -> int:
        """Attempt to detect available system memory in MiB.

        Returns
        -------
        int
            Available memory in MiB, or a conservative default (512)
            if detection is not supported on this platform.
        """
        try:
            import psutil  # type: ignore[import-not-found]

            return int(psutil.virtual_memory().available / (1024 * 1024))
        except ImportError:
            pass

        # Fallback: read /proc/meminfo on Linux
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        return kb // 1024
        except OSError:
            pass

        return 512  # Conservative default when detection is unavailable


__all__ = [
    "EdgeConfig",
    "EdgeRuntime",
    "PerformanceEstimate",
    "QuantizationLevel",
    "ResourceValidationResult",
]
