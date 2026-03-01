/**
 * HTTP client for the agent-sovereign deployment management API.
 *
 * Delegates all HTTP transport to `@aumos/sdk-core` which provides
 * automatic retry with exponential back-off, timeout management via
 * `AbortSignal.timeout`, interceptor support, and a typed error hierarchy.
 *
 * The public-facing `ApiResult<T>` envelope is preserved for full
 * backward compatibility with existing callers.
 *
 * @example
 * ```ts
 * import { createAgentSovereignClient } from "@aumos/agent-sovereign";
 *
 * const client = createAgentSovereignClient({ baseUrl: "http://localhost:8092" });
 *
 * const status = await client.getSovereigntyStatus("my-edge-node");
 *
 * if (status.ok) {
 *   console.log("Sovereignty level:", status.data.sovereignty_level);
 * }
 * ```
 */

import {
  createHttpClient,
  HttpError,
  NetworkError,
  TimeoutError,
  AumosError,
  type HttpClient,
} from "@aumos/sdk-core";

import type {
  ApiResult,
  DeploymentBundle,
  EdgeRuntime,
  OfflineCapability,
  PackagerConfig,
  PerformanceEstimate,
  ResourceValidationResult,
  SovereigntyLevel,
  SovereigntyStatus,
  SyncConfig,
  SyncStateRequest,
  SyncTask,
} from "./types.js";

// ---------------------------------------------------------------------------
// Client configuration
// ---------------------------------------------------------------------------

/** Configuration options for the AgentSovereignClient. */
export interface AgentSovereignClientConfig {
  /** Base URL of the agent-sovereign server (e.g. "http://localhost:8092"). */
  readonly baseUrl: string;
  /** Optional request timeout in milliseconds (default: 30000). */
  readonly timeoutMs?: number;
  /** Optional extra HTTP headers sent with every request. */
  readonly headers?: Readonly<Record<string, string>>;
}

// ---------------------------------------------------------------------------
// Internal adapter
// ---------------------------------------------------------------------------

async function callApi<T>(
  operation: () => Promise<{ readonly data: T; readonly status: number }>,
): Promise<ApiResult<T>> {
  try {
    const response = await operation();
    return { ok: true, data: response.data };
  } catch (error: unknown) {
    if (error instanceof HttpError) {
      return {
        ok: false,
        error: { error: error.message, detail: String(error.body ?? "") },
        status: error.statusCode,
      };
    }
    if (error instanceof TimeoutError) {
      return {
        ok: false,
        error: { error: "Request timed out", detail: error.message },
        status: 0,
      };
    }
    if (error instanceof NetworkError) {
      return {
        ok: false,
        error: { error: "Network error", detail: error.message },
        status: 0,
      };
    }
    if (error instanceof AumosError) {
      return {
        ok: false,
        error: { error: error.code, detail: error.message },
        status: error.statusCode ?? 0,
      };
    }
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      error: { error: "Unexpected error", detail: message },
      status: 0,
    };
  }
}

// ---------------------------------------------------------------------------
// Client interface
// ---------------------------------------------------------------------------

/** Typed HTTP client for the agent-sovereign server. */
export interface AgentSovereignClient {
  /**
   * Create a signed deployment bundle for a sovereign agent.
   *
   * @param config - Packager configuration including sovereignty level and file sources.
   * @returns The assembled DeploymentBundle with manifest and checksum.
   */
  createBundle(config: PackagerConfig): Promise<ApiResult<DeploymentBundle>>;

  /**
   * Deploy an agent bundle to an edge runtime.
   *
   * @param options - Bundle checksum, target edge node ID, and optional runtime overrides.
   * @returns The EdgeRuntime configuration that was applied.
   */
  deployEdge(options: {
    bundle_checksum: string;
    edge_node_id: string;
    sovereignty_level: SovereigntyLevel;
    runtime_overrides?: Partial<EdgeRuntime>;
  }): Promise<ApiResult<EdgeRuntime>>;

  /**
   * Get the current sovereignty status of an edge node.
   *
   * @param edgeNodeId - The edge node identifier.
   * @returns A SovereigntyStatus with current level, connectivity, and pending tasks.
   */
  getSovereigntyStatus(edgeNodeId: string): Promise<ApiResult<SovereigntyStatus>>;

  /**
   * Queue a state synchronisation task for an edge node.
   *
   * @param edgeNodeId - The edge node to sync.
   * @param request - Sync task specification.
   * @returns The created SyncTask record.
   */
  syncState(
    edgeNodeId: string,
    request: SyncStateRequest,
  ): Promise<ApiResult<SyncTask>>;

  /**
   * Get the offline capabilities of an edge deployment.
   *
   * @param edgeNodeId - The edge node identifier.
   * @returns The OfflineCapability descriptor for this deployment.
   */
  getOfflineCapabilities(edgeNodeId: string): Promise<ApiResult<OfflineCapability>>;

  /**
   * Validate resources for an edge runtime configuration.
   *
   * @param runtime - The EdgeRuntime configuration to validate.
   * @returns A ResourceValidationResult with errors and warnings.
   */
  validateResources(
    runtime: EdgeRuntime,
  ): Promise<ApiResult<ResourceValidationResult>>;

  /**
   * Estimate inference performance for a model on an edge runtime.
   *
   * @param options - Edge runtime config and model size in billions of parameters.
   * @returns A PerformanceEstimate with tokens/sec and latency projections.
   */
  estimatePerformance(options: {
    runtime: EdgeRuntime;
    model_parameter_count_billions: number;
  }): Promise<ApiResult<PerformanceEstimate>>;

  /**
   * Update the synchronisation policy for an edge node.
   *
   * @param edgeNodeId - The edge node identifier.
   * @param policy - The new SyncConfig to apply.
   * @returns The updated SyncConfig.
   */
  updateSyncPolicy(
    edgeNodeId: string,
    policy: SyncConfig,
  ): Promise<ApiResult<SyncConfig>>;
}

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

/**
 * Create a typed HTTP client for the agent-sovereign server.
 *
 * @param config - Client configuration including base URL.
 * @returns An AgentSovereignClient instance.
 */
export function createAgentSovereignClient(
  config: AgentSovereignClientConfig,
): AgentSovereignClient {
  const http: HttpClient = createHttpClient({
    baseUrl: config.baseUrl,
    timeout: config.timeoutMs ?? 30_000,
    defaultHeaders: config.headers,
  });

  return {
    createBundle(packagerConfig: PackagerConfig): Promise<ApiResult<DeploymentBundle>> {
      return callApi(() =>
        http.post<DeploymentBundle>("/sovereign/bundles", packagerConfig),
      );
    },

    deployEdge(options: {
      bundle_checksum: string;
      edge_node_id: string;
      sovereignty_level: SovereigntyLevel;
      runtime_overrides?: Partial<EdgeRuntime>;
    }): Promise<ApiResult<EdgeRuntime>> {
      return callApi(() =>
        http.post<EdgeRuntime>("/sovereign/edge/deploy", options),
      );
    },

    getSovereigntyStatus(edgeNodeId: string): Promise<ApiResult<SovereigntyStatus>> {
      return callApi(() =>
        http.get<SovereigntyStatus>(
          `/sovereign/edge/${encodeURIComponent(edgeNodeId)}/status`,
        ),
      );
    },

    syncState(
      edgeNodeId: string,
      request: SyncStateRequest,
    ): Promise<ApiResult<SyncTask>> {
      return callApi(() =>
        http.post<SyncTask>(
          `/sovereign/edge/${encodeURIComponent(edgeNodeId)}/sync`,
          request,
        ),
      );
    },

    getOfflineCapabilities(edgeNodeId: string): Promise<ApiResult<OfflineCapability>> {
      return callApi(() =>
        http.get<OfflineCapability>(
          `/sovereign/edge/${encodeURIComponent(edgeNodeId)}/offline`,
        ),
      );
    },

    validateResources(
      runtime: EdgeRuntime,
    ): Promise<ApiResult<ResourceValidationResult>> {
      return callApi(() =>
        http.post<ResourceValidationResult>(
          "/sovereign/edge/validate-resources",
          runtime,
        ),
      );
    },

    estimatePerformance(options: {
      runtime: EdgeRuntime;
      model_parameter_count_billions: number;
    }): Promise<ApiResult<PerformanceEstimate>> {
      return callApi(() =>
        http.post<PerformanceEstimate>(
          "/sovereign/edge/estimate-performance",
          options,
        ),
      );
    },

    updateSyncPolicy(
      edgeNodeId: string,
      policy: SyncConfig,
    ): Promise<ApiResult<SyncConfig>> {
      return callApi(() =>
        http.put<SyncConfig>(
          `/sovereign/edge/${encodeURIComponent(edgeNodeId)}/sync-policy`,
          policy,
        ),
      );
    },
  };
}
