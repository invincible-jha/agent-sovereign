/**
 * TypeScript interfaces for the agent-sovereign deployment manager.
 *
 * Mirrors the Python dataclasses and enums defined in:
 *   agent_sovereign.classifier.levels   (SovereigntyLevel)
 *   agent_sovereign.edge.runtime        (QuantizationLevel, EdgeConfig, ResourceValidationResult, PerformanceEstimate)
 *   agent_sovereign.edge.sync           (SyncPriority, SyncTaskStatus, SyncPolicy, SyncTask)
 *   agent_sovereign.edge.offline        (OfflineStatus, OfflineCapability, CachedResponse)
 *   agent_sovereign.deployment.packager (DeploymentManifest, DeploymentBundle)
 *
 * All interfaces use readonly fields to match Python frozen dataclasses.
 */

// ---------------------------------------------------------------------------
// Sovereignty level
// ---------------------------------------------------------------------------

/**
 * Sovereignty levels from least (cloud) to most (air-gapped) sovereign.
 * Maps to SovereigntyLevel IntEnum in Python.
 */
export type SovereigntyLevel =
  | "L1_CLOUD"
  | "L2_CLOUD_DEDICATED"
  | "L3_HYBRID"
  | "L4_LOCAL_AUGMENTED"
  | "L5_FULLY_LOCAL"
  | "L6_CLASSIFIED"
  | "L7_AIRGAPPED";

/** Numeric value (1–7) associated with a sovereignty level. */
export type SovereigntyLevelValue = 1 | 2 | 3 | 4 | 5 | 6 | 7;

// ---------------------------------------------------------------------------
// Edge runtime types
// ---------------------------------------------------------------------------

/**
 * Supported model quantization levels for edge inference.
 * Maps to QuantizationLevel enum in Python.
 */
export type QuantizationLevel =
  | "none"
  | "int8"
  | "int4"
  | "gguf_q4_k_m"
  | "gguf_q5_k_m"
  | "gguf_q8_0";

/** Configuration for an edge runtime environment. */
export interface EdgeRuntime {
  /** Maximum RAM available for model and inference (MiB). */
  readonly max_memory_mb: number;
  /** Maximum CPU utilisation percentage (0–100) allowed. */
  readonly max_cpu_percent: number;
  /** Quantization level to apply to loaded models. */
  readonly model_quantization: QuantizationLevel;
  /** Whether this edge node can operate without network connectivity. */
  readonly offline_capable: boolean;
  /** Maximum number of simultaneous inference requests. */
  readonly max_concurrent_requests: number;
  /** Path to the directory where model weights are cached locally. */
  readonly model_cache_dir: string;
  /** GPU memory available in MiB (0 if no GPU present). */
  readonly gpu_memory_mb: number;
  /** Whether to cache model activations across requests. */
  readonly enable_model_caching: boolean;
  /** How often the edge node sends a heartbeat in seconds. */
  readonly heartbeat_interval_seconds: number;
}

/** Result of a resource validation check for an EdgeRuntime. */
export interface ResourceValidationResult {
  /** True if all resource requirements are met. */
  readonly is_valid: boolean;
  /** Non-fatal issues detected during validation. */
  readonly warnings: readonly string[];
  /** Fatal issues that prevent the runtime from operating correctly. */
  readonly errors: readonly string[];
  /** Detected available system memory in MiB. */
  readonly available_memory_mb: number;
  /** Detected logical CPU count. */
  readonly available_cpu_count: number;
}

/** Estimated inference performance for an edge configuration. */
export interface PerformanceEstimate {
  /** Estimated token generation rate (tokens/second). */
  readonly tokens_per_second: number;
  /** Estimated latency to the first output token in milliseconds. */
  readonly time_to_first_token_ms: number;
  /** Estimated maximum context length supported given memory constraints. */
  readonly max_context_tokens: number;
  /** Estimated throughput multiplier from quantization (1.0 = no speedup). */
  readonly quantization_speedup_factor: number;
  /** Explanatory notes about the estimate. */
  readonly notes: readonly string[];
}

// ---------------------------------------------------------------------------
// Deployment bundle types
// ---------------------------------------------------------------------------

/** Structured manifest describing a deployment package. */
export interface DeploymentManifest {
  /** Unique identifier for this package. */
  readonly package_id: string;
  /** ISO-8601 timestamp of package creation. */
  readonly created_at: string;
  /** The sovereignty level this package targets. */
  readonly sovereignty_level: string;
  /** Name of the deployment template used. */
  readonly template_name: string;
  /** List of relative file paths included in the bundle. */
  readonly files: readonly string[];
  /** Additional key/value metadata attached to this package. */
  readonly metadata: Readonly<Record<string, string>>;
}

/** A complete deployment bundle ready for transfer or installation. */
export interface DeploymentBundle {
  /** Structured manifest document for the package. */
  readonly manifest: DeploymentManifest;
  /** Resolved list of file paths included. */
  readonly files_list: readonly string[];
  /** SHA-256 hex digest of the serialised manifest. */
  readonly checksum: string;
  /** The sovereignty level this package targets. */
  readonly sovereignty_level: SovereigntyLevel;
  /** The raw YAML string of the manifest. */
  readonly manifest_yaml: string;
}

/** Configuration for creating a deployment bundle. */
export interface PackagerConfig {
  /** The target sovereignty level for the deployment. */
  readonly sovereignty_level: SovereigntyLevel;
  /** Optional explicit package identifier. */
  readonly package_id?: string;
  /** Optional additional key/value pairs to embed in the manifest. */
  readonly metadata?: Readonly<Record<string, string>>;
  /** Optional source directory path to scan for files. */
  readonly source_directory?: string;
  /** Optional explicit list of file paths to include. */
  readonly explicit_files?: readonly string[];
}

// ---------------------------------------------------------------------------
// Synchronisation types
// ---------------------------------------------------------------------------

/**
 * Priority level for a sync task.
 * Maps to SyncPriority enum in Python.
 */
export type SyncPriority = "critical" | "high" | "normal" | "low";

/**
 * Lifecycle state of a sync task.
 * Maps to SyncTaskStatus enum in Python.
 */
export type SyncTaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "skipped";

/** Policy governing when and how synchronisation may occur. */
export interface SyncConfig {
  /** Whether sync tasks may run in the background. */
  readonly allow_background_sync: boolean;
  /** Maximum number of retry attempts for a failed sync task. */
  readonly max_retry_attempts: number;
  /** Base backoff interval in seconds between retry attempts. */
  readonly retry_backoff_seconds: number;
  /** UTC hour (0–23) at which the sync window opens. -1 means any time. */
  readonly sync_window_start_hour: number;
  /** UTC hour (0–23) at which the sync window closes. -1 means any time. */
  readonly sync_window_end_hour: number;
  /** Whether sync must only proceed over an encrypted channel. */
  readonly require_encrypted_channel: boolean;
  /** Maximum size of a single sync payload in MiB. */
  readonly max_payload_size_mb: number;
  /** If non-empty, only sync tasks with a type in this list are allowed. */
  readonly allowed_sync_types: readonly string[];
}

/** A single unit of work to synchronise. */
export interface SyncTask {
  /** Unique identifier for this sync task. */
  readonly task_id: string;
  /** Category of sync (e.g. "model_update", "audit_log"). */
  readonly sync_type: string;
  /** Human-readable description of what this task syncs. */
  readonly payload_description: string;
  /** Task priority affecting processing order. */
  readonly priority: SyncPriority;
  /** Current lifecycle state. */
  readonly status: SyncTaskStatus;
  /** ISO-8601 UTC timestamp of task creation. */
  readonly created_at: string;
  /** ISO-8601 UTC timestamp of last status change. */
  readonly updated_at: string;
  /** Number of retry attempts made so far. */
  readonly retry_count: number;
  /** Last error message if the task failed. */
  readonly error_message: string;
  /** Arbitrary key/value metadata attached to this task. */
  readonly metadata: Readonly<Record<string, string>>;
}

/** Request payload for queueing a sync task. */
export interface SyncStateRequest {
  /** Category of the sync task. */
  readonly sync_type: string;
  /** Human-readable description of what will be synced. */
  readonly payload_description: string;
  /** Task priority. */
  readonly priority?: SyncPriority;
  /** Optional metadata key/value pairs. */
  readonly metadata?: Readonly<Record<string, string>>;
}

// ---------------------------------------------------------------------------
// Offline capability types
// ---------------------------------------------------------------------------

/**
 * Current connectivity status of the edge node.
 * Maps to OfflineStatus enum in Python.
 */
export type OfflineStatus = "online" | "offline" | "degraded";

/** Describes the offline operation capabilities of an edge deployment. */
export interface OfflineCapability {
  /** Whether the node can return cached responses when offline. */
  readonly can_serve_cached_responses: boolean;
  /** Whether local model inference is available without network. */
  readonly can_run_local_inference: boolean;
  /** Whether write operations can be queued for later sync. */
  readonly can_queue_writes: boolean;
  /** Maximum hours the node should operate offline. -1 = indefinite. */
  readonly max_offline_duration_hours: number;
  /** Time-to-live for cached responses in hours. */
  readonly cache_ttl_hours: number;
  /** Operation types available in degraded/offline mode. */
  readonly supported_degraded_operations: readonly string[];
}

/** Current sovereignty status of an edge deployment. */
export interface SovereigntyStatus {
  /** The sovereignty level currently in effect. */
  readonly sovereignty_level: SovereigntyLevel;
  /** Current connectivity status. */
  readonly offline_status: OfflineStatus;
  /** Number of sync tasks currently pending. */
  readonly pending_sync_tasks: number;
  /** Whether resource validation has passed. */
  readonly resources_valid: boolean;
  /** ISO-8601 UTC timestamp of the last status check. */
  readonly checked_at: string;
}

// ---------------------------------------------------------------------------
// API result wrapper (shared pattern)
// ---------------------------------------------------------------------------

/** Standard error payload returned by the agent-sovereign API. */
export interface ApiError {
  readonly error: string;
  readonly detail: string;
}

/** Result type for all client operations. */
export type ApiResult<T> =
  | { readonly ok: true; readonly data: T }
  | { readonly ok: false; readonly error: ApiError; readonly status: number };
