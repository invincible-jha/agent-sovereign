#!/usr/bin/env python3
"""Example: Edge Runtime and Offline Management

Demonstrates configuring an edge runtime, validating resources,
and managing offline capabilities with sync policies.

Usage:
    python examples/05_edge_runtime.py

Requirements:
    pip install agent-sovereign
"""
from __future__ import annotations

import agent_sovereign
from agent_sovereign import (
    CachedResponse,
    EdgeConfig,
    EdgeRuntime,
    OfflineCapability,
    OfflineManager,
    OfflineStatus,
    QuantizationLevel,
    SyncManager,
    SyncPolicy,
    SyncPriority,
    SyncTask,
)


def main() -> None:
    print(f"agent-sovereign version: {agent_sovereign.__version__}")

    # Step 1: Configure edge runtime
    config = EdgeConfig(
        device_id="edge-node-eu-01",
        available_memory_gb=8.0,
        available_cpu_cores=4,
        has_gpu=False,
        quantization=QuantizationLevel.INT8,
        max_model_size_gb=4.0,
    )
    runtime = EdgeRuntime(config=config)
    print(f"Edge runtime: device={config.device_id}")
    print(f"  Quantization: {config.quantization.value}")

    # Step 2: Validate resource fit for models
    models_to_check = [
        {"model_id": "local-llm-7b", "size_gb": 3.5, "min_memory_gb": 6.0},
        {"model_id": "local-llm-13b", "size_gb": 7.0, "min_memory_gb": 12.0},
        {"model_id": "local-embedder", "size_gb": 0.5, "min_memory_gb": 1.0},
    ]

    print("\nResource validation:")
    for model in models_to_check:
        result = runtime.validate_resource_fit(
            model_id=str(model["model_id"]),
            model_size_gb=float(model["size_gb"]),  # type: ignore[arg-type]
            min_memory_gb=float(model["min_memory_gb"]),  # type: ignore[arg-type]
        )
        fits = result.fits
        print(f"  {model['model_id']} ({model['size_gb']}GB): "
              f"{'FITS' if fits else 'DOES NOT FIT'}")
        if not fits:
            print(f"    Reason: {result.reason}")

    # Step 3: Offline management
    offline_manager = OfflineManager()
    capabilities = [
        OfflineCapability(name="text-summarisation", priority=1),
        OfflineCapability(name="document-qa", priority=2),
        OfflineCapability(name="entity-extraction", priority=1),
    ]
    for cap in capabilities:
        offline_manager.register(cap)

    offline_manager.set_status(OfflineStatus.OFFLINE)
    available = offline_manager.get_available_capabilities()
    print(f"\nOffline mode: {len(available)} capabilities available")
    for cap in available:
        print(f"  {cap.name} (priority={cap.priority})")

    # Cache a response
    cached = CachedResponse(
        query="What is the Q3 revenue?",
        response="Q3 revenue was $12.4M.",
        ttl_seconds=3600,
    )
    offline_manager.cache(cached)
    hit = offline_manager.get_cached("What is the Q3 revenue?")
    print(f"\nCache hit: {hit is not None} — '{hit.response[:40] if hit else 'N/A'}'")

    # Step 4: Sync policy
    sync_manager = SyncManager()
    sync_manager.set_policy(SyncPolicy(
        interval_seconds=300,
        priority=SyncPriority.NORMAL,
        retry_on_failure=True,
    ))
    task = SyncTask(
        task_id="sync-model-weights",
        description="Sync updated model weights from central registry.",
        priority=SyncPriority.HIGH,
    )
    sync_manager.enqueue(task)
    print(f"\nSync queue: {sync_manager.pending_count()} task(s) pending")


if __name__ == "__main__":
    main()
