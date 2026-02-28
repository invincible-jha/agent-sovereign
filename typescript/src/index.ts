/**
 * @aumos/agent-sovereign
 *
 * TypeScript client for the AumOS agent-sovereign deployment manager.
 * Provides HTTP client, sovereignty level types, edge runtime configuration,
 * offline capabilities, and state synchronisation type definitions.
 */

// Client and configuration
export type { AgentSovereignClient, AgentSovereignClientConfig } from "./client.js";
export { createAgentSovereignClient } from "./client.js";

// Core types
export type {
  ApiError,
  ApiResult,
  DeploymentBundle,
  DeploymentManifest,
  EdgeRuntime,
  OfflineCapability,
  OfflineStatus,
  PackagerConfig,
  PerformanceEstimate,
  QuantizationLevel,
  ResourceValidationResult,
  SovereigntyLevel,
  SovereigntyLevelValue,
  SovereigntyStatus,
  SyncConfig,
  SyncPriority,
  SyncStateRequest,
  SyncTask,
  SyncTaskStatus,
} from "./types.js";
