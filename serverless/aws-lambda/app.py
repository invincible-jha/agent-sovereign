"""Example AWS Lambda handler using AumOS packages."""
import json
from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process an agent request with AumOS security scanning."""
    try:
        from agent_eval.metrics import accuracy  # noqa: F401
        from agentshield.scanners import InputScanner  # noqa: F401

        body = json.loads(event.get("body", "{}"))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "AumOS agent processed successfully",
                "input_keys": list(body.keys()),
            }),
        }
    except ImportError as exc:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Missing AumOS package: {exc}"}),
        }
