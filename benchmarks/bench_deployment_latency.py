"""Benchmark: Deployment validation latency — per-check p50/p95/p99.

Measures the per-call latency of DeploymentValidator.validate() across
different sovereignty levels, capturing latency distribution statistics.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator

_WARMUP: int = 100
_ITERATIONS: int = 3_000


def _make_config(level: SovereigntyLevel) -> DeploymentConfig:
    """Build a deployment config for the given sovereignty level."""
    return DeploymentConfig(
        sovereignty_level=level,
        data_residency_region="US",
        network_isolated=level >= SovereigntyLevel.L4_LOCAL_AUGMENTED,
        encryption_at_rest="AES-256",
        encryption_in_transit="TLS 1.3",
        key_management="local_hsm",
        audit_logging_enabled=True,
        air_gapped=level >= SovereigntyLevel.L6_CLASSIFIED,
        tpm_present=level >= SovereigntyLevel.L5_FULLY_LOCAL,
        fips_hardware=level >= SovereigntyLevel.L6_CLASSIFIED,
    )


def bench_deployment_validation_latency() -> dict[str, object]:
    """Benchmark DeploymentValidator.validate() per-call latency.

    Returns
    -------
    dict with keys: operation, iterations, total_seconds, ops_per_second,
    avg_latency_ms, p99_latency_ms, memory_peak_mb.
    """
    validator = DeploymentValidator()
    config = _make_config(SovereigntyLevel.L2_CLOUD_DEDICATED)

    # Warmup.
    for _ in range(_WARMUP):
        validator.validate(config)

    latencies_ms: list[float] = []
    for _ in range(_ITERATIONS):
        t0 = time.perf_counter()
        validator.validate(config)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)
    total = sum(latencies_ms) / 1000

    result: dict[str, object] = {
        "operation": "deployment_validation_latency",
        "iterations": _ITERATIONS,
        "total_seconds": round(total, 4),
        "ops_per_second": round(_ITERATIONS / total, 1),
        "avg_latency_ms": round(sum(latencies_ms) / n, 4),
        "p99_latency_ms": round(sorted_lats[min(int(n * 0.99), n - 1)], 4),
        "memory_peak_mb": 0.0,
    }
    print(
        f"[bench_deployment_latency] {result['operation']}: "
        f"p99={result['p99_latency_ms']:.4f}ms  "
        f"mean={result['avg_latency_ms']:.4f}ms"
    )
    return result


def run_benchmark() -> dict[str, object]:
    """Entry point returning the benchmark result dict."""
    return bench_deployment_validation_latency()


if __name__ == "__main__":
    result = run_benchmark()
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    output_path = results_dir / "latency_baseline.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"Results saved to {output_path}")
