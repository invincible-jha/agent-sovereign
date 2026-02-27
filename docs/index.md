# agent-sovereign

Sovereign & Edge Deployment Toolkit — one-command bundling, offline mode, edge runtime, and data residency controls for AI agents.

[![CI](https://github.com/invincible-jha/agent-sovereign/actions/workflows/ci.yaml/badge.svg)](https://github.com/invincible-jha/agent-sovereign/actions/workflows/ci.yaml)
[![PyPI version](https://img.shields.io/pypi/v/agent-sovereign.svg)](https://pypi.org/project/agent-sovereign/)
[![Python versions](https://img.shields.io/pypi/pyversions/agent-sovereign.svg)](https://pypi.org/project/agent-sovereign/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

---

## Installation

```bash
pip install agent-sovereign
```

Verify the installation:

```bash
agent-sovereign version
```

---

## Quick Start

```python
import agent_sovereign

# See examples/01_quickstart.py for a working example
```

---

## Key Features

- **Data sensitivity classifier** assigns INFORMATIONAL, ADVISORY, or DECISION_SUPPORT risk tiers based on regulatory rules (HIPAA, GDPR, financial regulations) to determine what data may leave a sovereign boundary
- **AgentPackager** bundles an agent with its model weights, tools, and config into a self-contained deployment artifact targeting Docker, Kubernetes, Lambda, or bare-metal edge nodes
- **EdgeRuntime** validates hardware resource constraints (RAM, CPU, GPU), selects the appropriate quantization level (INT4, INT8, GGUF variants), and manages model caching for offline inference
- **EdgeSync** orchestrates delta synchronization of knowledge and model updates between edge nodes and a central coordinator, with offline-capable operation when network connectivity is unavailable
- **Data residency policy engine** enforces where data may be stored and processed, mapping sensitivity tiers to approved geographic regions
- **Provenance attestation** generates signed attestation records for every model inference, establishing a verifiable chain of custody from training data to deployed output
- **Deployment validator** checks a packaged agent against residency policies, capability declarations, and hardware constraints before authorizing a deployment

---

## Links

- [GitHub Repository](https://github.com/invincible-jha/agent-sovereign)
- [PyPI Package](https://pypi.org/project/agent-sovereign/)
- [Architecture](architecture.md)
- [Changelog](https://github.com/invincible-jha/agent-sovereign/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/invincible-jha/agent-sovereign/blob/main/CONTRIBUTING.md)

---

> Part of the [AumOS](https://github.com/aumos-ai) open-source agent infrastructure portfolio.
