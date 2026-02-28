# AumOS Agents on Cloudflare Workers

This directory contains a Cloudflare Workers deployment that proxies agent requests
to an AumOS API endpoint, stores audit logs in R2, and runs at the edge for
low-latency access globally.

## Overview

Cloudflare Workers execute JavaScript/TypeScript at the edge in V8 isolates.
Because AumOS core packages are Python-based, the worker acts as a thin edge
layer that:

1. Validates and rate-limits incoming requests.
2. Forwards payloads to a backend AumOS API (e.g., an AWS Lambda or a VPC service).
3. Writes structured audit logs to an R2 bucket for compliance.

## Prerequisites

- Node.js 18+
- A Cloudflare account with Workers and R2 enabled
- Wrangler CLI: `npm install -g wrangler`
- An AumOS API endpoint (URL set via `AUMOS_API_URL` variable)

## Setup

```bash
# Install dependencies
npm install

# Authenticate with Cloudflare
wrangler login

# Create the R2 bucket (first time only)
wrangler r2 bucket create aumos-agents
```

## Local Development

```bash
npm run dev
```

Wrangler starts a local dev server at `http://localhost:8787`. Send a POST request:

```bash
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{"action": "evaluate", "payload": {"prompt": "hello"}}'
```

## Deploy to Production

```bash
npm run deploy
```

Wrangler bundles `src/worker.ts`, uploads it to Cloudflare, and prints the
worker URL (e.g., `https://aumos-agent-worker.<your-subdomain>.workers.dev`).

## Configuration

Edit `wrangler.toml` to set the `AUMOS_API_URL` variable before deploying:

```toml
[vars]
AUMOS_API_URL = "https://your-aumos-api.example.com"
```

For secrets (API keys, tokens), use Wrangler secrets instead of `[vars]`:

```bash
wrangler secret put AUMOS_API_KEY
```

Then access `env.AUMOS_API_KEY` in `worker.ts`.

## R2 Audit Logs

Every processed request writes a JSON audit record to the `aumos-agents` R2 bucket
under the key `audit/<unix-timestamp-ms>.json`. Retrieve logs with:

```bash
wrangler r2 object get aumos-agents audit/1706745600000.json
```

Or list all audit keys:

```bash
wrangler r2 object list aumos-agents --prefix audit/
```

## Request Format

```json
{
  "action": "evaluate",
  "payload": {
    "prompt": "...",
    "context": {}
  }
}
```

## Response Format

```json
{
  "status": "success",
  "result": { ... },
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```

## TypeScript Types

`src/worker.ts` is fully typed with strict TypeScript. The `Env` interface matches
the bindings declared in `wrangler.toml`. Extend `AgentRequest` and `AgentResponse`
to match your AumOS API contract.

## Limits

| Resource            | Workers Free | Workers Paid |
|---------------------|--------------|--------------|
| Requests/day        | 100,000      | Unlimited    |
| CPU time/request    | 10 ms        | 50 ms        |
| Memory/isolate      | 128 MB       | 128 MB       |
| R2 writes/month     | 1M           | Pay-as-you-go|

For long-running evaluations, consider using Workers with Durable Objects or
offloading compute to the backend AumOS API service.

## License

Apache 2.0 — see repo root `LICENSE`.
