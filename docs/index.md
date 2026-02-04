# RouteKitAI

**A minimal, production-ready framework for building and orchestrating AI agents.**

RouteKitAI provides graph-based orchestration, built-in tracing, and deterministic replay so you can build, observe, and test agents with confidence.

## Features

- **Graph-native orchestration** — Workflows as explicit graphs with clear control flow
- **Automatic tracing** — Every run produces an immutable trace log
- **Deterministic replay** — Reproduce any run for testing and debugging
- **Policy system** — ReAct, Supervisor, Graph, and custom policies
- **CLI tools** — Run, trace, replay, and analyze from the command line

## Quick start

```bash
pip install RouteKitAI
```

```python
import asyncio
from routekitai import Agent
from routekitai.providers.local import FakeModel
from routekitai.core.tools import EchoTool

model = FakeModel(name="test")
model.add_response("Hello from RouteKitAI!")
agent = Agent(name="my_agent", model=model, tools=[EchoTool()])

async def main():
    result = await agent.run("Hello!")
    print(result.output.content)

asyncio.run(main())
```

## Documentation

- **[Getting started](getting-started.md)** — Installation, first agent, first graph
- **Guides**
  - [Running agents](guides/running-agents.md) — `run`, `run_stream`, Runtime, policies
  - [Creating tools](guides/creating-tools.md) — Define tools with Pydantic, permissions, redaction
  - [Graph workflows](guides/graph-workflows.md) — Graphs, nodes, edges, GraphPolicy
  - [Tracing and replay](guides/tracing-and-replay.md) — Trace IDs, CLI, replay for tests
  - [CLI reference](guides/cli-reference.md) — All `routekitai` commands
  - [Providers](guides/providers.md) — FakeModel, OpenAI, env vars
- **[Architecture](architecture.md)** — Design, execution model, and core components
- **[Security & Governance](security-and-governance.md)** — Policy hooks, PII redaction, tool filtering, and best practices
- **[API reference](api-reference.md)** — Main classes and modules

## Links

- [GitHub](https://github.com/MedGhassen/RouteKitAI)
- [PyPI](https://pypi.org/project/RouteKitAI/)
- [Issues](https://github.com/MedGhassen/RouteKitAI/issues)
