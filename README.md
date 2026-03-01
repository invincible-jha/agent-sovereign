# agent-sovereign

Sovereign and edge deployment toolkit for self-contained agent bundles

[![CI](https://github.com/aumos-ai/agent-sovereign/actions/workflows/ci.yaml/badge.svg)](https://github.com/aumos-ai/agent-sovereign/actions/workflows/ci.yaml)
[![PyPI version](https://img.shields.io/pypi/v/agent-sovereign.svg)](https://pypi.org/project/agent-sovereign/)
[![Python versions](https://img.shields.io/pypi/pyversions/agent-sovereign.svg)](https://pypi.org/project/agent-sovereign/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Part of the [AumOS](https://github.com/aumos-ai) open-source agent infrastructure portfolio.

---

## Features

- Data sensitivity classifier assigns INFORMATIONAL, ADVISORY, or DECISION_SUPPORT risk tiers based on regulatory rules (HIPAA, GDPR, financial regulations) to determine what data may leave a sovereign boundary
- `AgentPackager` bundles an agent with its model weights, tools, and config into a self-contained deployment artifact targeting Docker, Kubernetes, Lambda, or bare-metal edge nodes
- `EdgeRuntime` validates hardware resource constraints (RAM, CPU, GPU), selects the appropriate quantization level (INT4, INT8, GGUF variants), and manages model caching for offline inference
- `EdgeSync` orchestrates delta synchronization of knowledge and model updates between edge nodes and a central coordinator, with offline-capable operation when network connectivity is unavailable
- Data residency policy engine enforces where data may be stored and processed, mapping sensitivity tiers to approved geographic regions
- Provenance attestation generates signed attestation records for every model inference, establishing a verifiable chain of custody from training data to deployed output
- Deployment validator checks a packaged agent against residency policies, capability declarations, and hardware constraints before authorizing a deployment

## Current Limitations

> **Transparency note**: We list known limitations to help you evaluate fit.

- **Benchmarks**: No published scalability or performance benchmarks.
- **Platforms**: Docker, K8s, Lambda, edge — no native Windows deployment.
- **Monitoring**: Basic health checks — no integrated observability.

## Quick Start

Install from PyPI:

```bash
pip install agent-sovereign
```

Verify the installation:

```bash
agent-sovereign version
```

Basic usage:

```python
import agent_sovereign

# See examples/01_quickstart.py for a working example
```

## Documentation

- [Architecture](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Examples](examples/README.md)

## Enterprise Upgrade

For production deployments requiring SLA-backed support and advanced
integrations, contact the maintainers or see the commercial extensions documentation.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
before opening a pull request.

## License

Apache 2.0 — see [LICENSE](LICENSE) for full terms.

---

Part of [AumOS](https://github.com/aumos-ai) — open-source agent infrastructure.
