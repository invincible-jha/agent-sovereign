export interface Env {
  AUMOS_API_URL: string;
  AGENT_STORAGE: R2Bucket;
}

interface AgentRequest {
  action: string;
  payload: Record<string, unknown>;
}

interface AgentResponse {
  status: string;
  result: Record<string, unknown>;
  timestamp: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "Method not allowed" }), {
        status: 405,
        headers: { "Content-Type": "application/json" },
      });
    }

    try {
      const body = await request.json() as AgentRequest;

      // Forward to AumOS API for processing
      const aumsResponse = await fetch(`${env.AUMOS_API_URL}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const result = await aumsResponse.json() as Record<string, unknown>;

      const response: AgentResponse = {
        status: "success",
        result,
        timestamp: new Date().toISOString(),
      };

      // Store audit log in R2
      await env.AGENT_STORAGE.put(
        `audit/${Date.now()}.json`,
        JSON.stringify(response)
      );

      return new Response(JSON.stringify(response), {
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      return new Response(
        JSON.stringify({ error: "Processing failed", details: String(error) }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};
