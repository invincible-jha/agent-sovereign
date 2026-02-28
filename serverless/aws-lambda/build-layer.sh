#!/usr/bin/env bash
# Build an AWS Lambda layer containing AumOS packages
# Usage: ./build-layer.sh [package1] [package2] ...
# Example: ./build-layer.sh aumos-agent-eval agent-gov aumos-agentshield

set -euo pipefail

PACKAGES="${@:-aumos-agent-eval agent-gov aumos-agentshield}"
LAYER_DIR="$(mktemp -d)"
PYTHON_DIR="$LAYER_DIR/python"

mkdir -p "$PYTHON_DIR"

echo "Installing packages: $PACKAGES"
pip install --target "$PYTHON_DIR" $PACKAGES --no-cache-dir

echo "Building layer ZIP..."
cd "$LAYER_DIR"
zip -r9 "$(pwd)/aumos-lambda-layer.zip" python/

echo "Layer built: $LAYER_DIR/aumos-lambda-layer.zip"
echo "Upload with: aws lambda publish-layer-version --layer-name aumos-agents --zip-file fileb://aumos-lambda-layer.zip --compatible-runtimes python3.10 python3.11 python3.12"
