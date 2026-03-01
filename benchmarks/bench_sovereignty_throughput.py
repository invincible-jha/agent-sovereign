"""Benchmark: Sovereignty compliance check throughput — checks per second.

Measures how many DeploymentValidator.validate() calls can be completed per
second against a standard L3_HYBRID deployment configuration.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_sovereign.classifier.levels import SovereigntyLevel
from agent_sovereign.deployment.validator import DeploymentConfig, DeploymentValidator

_ITERATIONS: int = 5_000


def _make_config() -> DeploymentConfig:
    """Build a standard L3_HYBRID deployment config for benchmarking."""
    return DeploymentConfig(
        sovereignty_level=SovereigntyLevel.L3_HYBRID,
        data_residency_region="EU",
        network_isolated=False,
        encryption_at_rest="AES-256",
        encryption_in_transit="TLS 1.3",
        key_management="local_hsm",
        audit_logging_enabled=True,
    )


def bench_sovereignty_check_throughput() -> dict[str, object]:
    """Benchmark DeploymentValidator.validate() throughput.

    Returns
    -------
    dict with keys: operation, iterations, total_seconds, ops_per_second,
    avg_latency_ms, p99_latency_ms, memory_peak_mb.
    """
    validator = DeploymentValidator()
    config = _make_config()

    start = time.perf_counter()
    for _ in range(_ITERATIONS):
        validator.validate(config)
    total = time.perf_counter() - start

    result: dict[str, object] = {
        "operation": "sovereignty_check_throughput",
        "iterations": _ITERATIONS,
        "total_seconds": round(total, 4),
        "ops_per_second": round(_ITERATIONS / total, 1),
        "avg_latency_ms": round(total / _ITERATIONS * 1000, 4),
        "p99_latency_ms": 0.0,
        "memory_peak_mb": 0.0,
    }
    print(
        f"[bench_sovereignty_throughput] {result['operation']}: "
        f"{result['ops_per_second']:,.0f} ops/sec  "
        f"avg {result['avg_latency_ms']:.4f} ms"
    )
    return result


def run_benchmark() -> dict[str, object]:
    """Entry point returning the benchmark result dict."""
    return bench_sovereignty_check_throughput()


if __name__ == "__main__":
    result = run_benchmark()
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    output_path = results_dir / "throughput_baseline.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"Results saved to {output_path}")
