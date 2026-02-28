# AumOS Packages as AWS Lambda Layers

This directory contains tooling for deploying AumOS packages as AWS Lambda layers,
enabling serverless agent workloads with security scanning, evaluation, and governance.

## Overview

Lambda layers let you package AumOS dependencies separately from your function code.
This reduces deployment package size, enables sharing across functions, and speeds up
cold starts by caching the layer across invocations.

## Prerequisites

- AWS CLI configured with appropriate permissions
- AWS SAM CLI for `template.yaml`-based deployments
- Python 3.10, 3.11, or 3.12
- `pip` available on PATH

## Build the Layer

Run `build-layer.sh` to produce a ZIP file ready for upload:

```bash
# Default packages: aumos-agent-eval agent-gov aumos-agentshield
./build-layer.sh

# Custom package set
./build-layer.sh aumos-agent-eval agent-gov aumos-agentshield aumos-agentcore-sdk
```

The script writes `aumos-lambda-layer.zip` to a temporary directory and prints
the upload command at the end.

## Publish the Layer

```bash
aws lambda publish-layer-version \
  --layer-name aumos-agents \
  --zip-file fileb://aumos-lambda-layer.zip \
  --compatible-runtimes python3.10 python3.11 python3.12
```

Note the `LayerVersionArn` in the output — you will reference it in your function
configuration or SAM template.

## Deploy with SAM

```bash
# Build
sam build

# Deploy interactively (first time)
sam deploy --guided

# Subsequent deploys
sam deploy
```

`template.yaml` defines:
- `AumOSLayer` — the layer built from the local ZIP
- `AgentFunction` — an example function that imports AumOS packages

## Use in Existing Functions

Attach the published layer ARN to any existing Lambda function:

```bash
aws lambda update-function-configuration \
  --function-name my-agent-function \
  --layers arn:aws:lambda:us-east-1:123456789012:layer:aumos-agents:1
```

## Example Handler

See `app.py` for a minimal handler that imports `agent_eval` and `agentshield`.
Extend the handler body to run evaluations, policy checks, or full agent loops
using the AumOS SDK.

## Compatible Runtimes

| Runtime   | Supported |
|-----------|-----------|
| python3.10 | Yes      |
| python3.11 | Yes      |
| python3.12 | Yes      |

## Size Limits

AWS Lambda layers have a 50 MB (ZIP) / 250 MB (unzipped) limit per layer and a
250 MB total limit across all layers attached to a function. Install only the
AumOS packages your function needs to stay within limits.

## Environment Variables

Set these on your Lambda function to configure AumOS at runtime:

| Variable                | Description                          |
|-------------------------|--------------------------------------|
| `AUMOS_LOG_LEVEL`       | Logging verbosity (`INFO`, `DEBUG`)  |
| `AUMOS_SHIELD_ENABLED`  | Enable/disable agentshield scanning  |
| `AUMOS_EVAL_THRESHOLD`  | Minimum passing score for evals      |

## License

Apache 2.0 — see repo root `LICENSE`.
