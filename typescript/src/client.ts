/**
 * HTTP client for the agent-sovereign deployment management API.
 *
 * Uses the Fetch API (available natively in Node 18+, browsers, and Deno).
 * No external dependencies required.
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

import type {
  ApiError,
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
// Internal helpers
// ---------------------------------------------------------------------------

async function fetchJson<T>(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(timeoutId);

    const body = await response.json() as unknown;

    if (!response.ok) {
      const errorBody = body as Partial<ApiError>;
      return {
        ok: false,
        error: {
          error: errorBody.error ?? "Unknown error",
          detail: errorBody.detail ?? "",
        },
        status: response.status,
      };
    }

    return { ok: true, data: body as T };
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      error: { error: "Network error", detail: message },
      status: 0,
    };
  }
}

function buildHeaders(
  extraHeaders: Readonly<Record<string, string>> | undefined,
): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...extraHeaders,
  };
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
  const { baseUrl, timeoutMs = 30_000, headers: extraHeaders } = config;
  const baseHeaders = buildHeaders(extraHeaders);

  return {
    async createBundle(
      packagerConfig: PackagerConfig,
    ): Promise<ApiResult<DeploymentBundle>> {
      return fetchJson<DeploymentBundle>(
        `${baseUrl}/sovereign/bundles`,
        {
          method: "POST",
          headers: baseHeaders,
          body: JSON.stringify(packagerConfig),
        },
        timeoutMs,
      );
    },

    async deployEdge(options: {
      bundle_checksum: string;
      edge_node_id: string;
      sovereignty_level: SovereigntyLevel;
      runtime_overrides?: Partial<EdgeRuntime>;
    }): Promise<ApiResult<EdgeRuntime>> {
      return fetchJson<EdgeRuntime>(
        `${baseUrl}/sovereign/edge/deploy`,
        {
          method: "POST",
          headers: baseHeaders,
          body: JSON.stringify(options),
        },
        timeoutMs,
      );
    },

    async getSovereigntyStatus(
      edgeNodeId: string,
    ): Promise<ApiResult<SovereigntyStatus>> {
      return fetchJson<SovereigntyStatus>(
        `${baseUrl}/sovereign/edge/${encodeURIComponent(edgeNodeId)}/status`,
        { method: "GET", headers: baseHeaders },
        timeoutMs,
      );
    },

    async syncState(
      edgeNodeId: string,
      request: SyncStateRequest,
    ): Promise<ApiResult<SyncTask>> {
      return fetchJson<SyncTask>(
        `${baseUrl}/sovereign/edge/${encodeURIComponent(edgeNodeId)}/sync`,
        {
          method: "POST",
          headers: baseHeaders,
          body: JSON.stringify(request),
        },
        timeoutMs,
      );
    },

    async getOfflineCapabilities(
      edgeNodeId: string,
    ): Promise<ApiResult<OfflineCapability>> {
      return fetchJson<OfflineCapability>(
        `${baseUrl}/sovereign/edge/${encodeURIComponent(edgeNodeId)}/offline`,
        { method: "GET", headers: baseHeaders },
        timeoutMs,
      );
    },

    async validateResources(
      runtime: EdgeRuntime,
    ): Promise<ApiResult<ResourceValidationResult>> {
      return fetchJson<ResourceValidationResult>(
        `${baseUrl}/sovereign/edge/validate-resources`,
        {
          method: "POST",
          headers: baseHeaders,
          body: JSON.stringify(runtime),
        },
        timeoutMs,
      );
    },

    async estimatePerformance(options: {
      runtime: EdgeRuntime;
      model_parameter_count_billions: number;
    }): Promise<ApiResult<PerformanceEstimate>> {
      return fetchJson<PerformanceEstimate>(
        `${baseUrl}/sovereign/edge/estimate-performance`,
        {
          method: "POST",
          headers: baseHeaders,
          body: JSON.stringify(options),
        },
        timeoutMs,
      );
    },

    async updateSyncPolicy(
      edgeNodeId: string,
      policy: SyncConfig,
    ): Promise<ApiResult<SyncConfig>> {
      return fetchJson<SyncConfig>(
        `${baseUrl}/sovereign/edge/${encodeURIComponent(edgeNodeId)}/sync-policy`,
        {
          method: "PUT",
          headers: baseHeaders,
          body: JSON.stringify(policy),
        },
        timeoutMs,
      );
    },
  };
}

/** Re-export types for convenience. */
export type {
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
};
