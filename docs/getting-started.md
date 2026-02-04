# Getting Started

This guide gets you from zero to running your first agent and first graph in RouteKitAI.

## Installation

Install the package from PyPI:

```bash
pip install RouteKitAI
```

For development (CLI, tests, type checking):

```bash
pip install "RouteKitAI[dev]"
```

Optional extras:

- **`[ui]`** — Web UI for traces (`routekitai serve`): FastAPI, Uvicorn
- **`[optional]`** — Vector memory, OpenAI/Anthropic adapters: sentence-transformers, faiss, openai, etc.

```bash
pip install "RouteKitAI[dev,ui,optional]"
```

**Requirements:** Python 3.11+, Pydantic 2.x.

## Your first agent

A minimal agent needs a **model** and optionally **tools**. RouteKitAI uses a provider-agnostic `Model` interface, so you can start with a fake model (no API key) and later switch to OpenAI, Anthropic, or your own backend.

```python
import asyncio
from routekitai import Agent
from routekitai.core.tools import EchoTool
from routekitai.providers.local import FakeModel

async def main():
    # Local fake model (no API key)
    model = FakeModel(name="basic")
    model.add_response("Hello! I used the echo tool.")

    agent = Agent(
        name="assistant",
        model=model,
        tools=[EchoTool()],
    )

    result = await agent.run("Say hello and echo 'RouteKit works!'")
    print(result.output.content)
    print("Trace ID:", result.trace_id)

asyncio.run(main())
```

- **`agent.run(prompt)`** — Runs the agent and returns a `RunResult` with `output`, `trace_id`, `messages`, and `final_state`.
- Every run is **traced** by default; traces are written under `.routekit/traces/` unless you set `trace_dir` on the agent.

## Your first graph

Graphs define **explicit workflows** as nodes (model, tool, subgraph, condition) and edges. Use `GraphPolicy` with a `Runtime` and registered agents.

```python
import asyncio
from pathlib import Path
from routekitai import Agent
from routekitai.core.policies import GraphPolicy
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.graphs import Graph, GraphNode, GraphEdge, NodeType
from routekitai.providers.local import FakeModel

async def main():
    model = FakeModel(name="m1")
    model.add_response("Processing...")
    agent = Agent(name="worker", model=model, tools=[EchoTool()])

    graph = Graph(
        name="example",
        entry_node="start",
        exit_node="end",
        nodes=[
            GraphNode(id="start", type=NodeType.MODEL, agent_name="worker",
                     output_mapping={"output": "result"}),
            GraphNode(id="end", type=NodeType.MODEL, agent_name="worker",
                     input_mapping={"result": "input"}, output_mapping={"output": "final"}),
        ],
        edges=[
            GraphEdge(source="start", target="end"),
        ],
    )

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(agent)
    policy = GraphPolicy(graph=graph)

    result = await runtime.run("worker", "Hello", policy=policy)
    print(result.output.content)
    print("Trace ID:", result.trace_id)

asyncio.run(main())
```

In practice you’ll often build the graph and policy once, then call `runtime.run(...)` with the appropriate agent and policy. See [Graph workflows](guides/graph-workflows.md) for full details.

## Next steps

- **[Running agents](guides/running-agents.md)** — `run` vs `run_stream`, using `Runtime` directly, trace directory.
- **[Creating tools](guides/creating-tools.md)** — Define tools with Pydantic input/output, permissions, redaction.
- **[Graph workflows](guides/graph-workflows.md)** — Nodes, edges, state mapping, `GraphPolicy`, subgraphs.
- **[Tracing and replay](guides/tracing-and-replay.md)** — Trace IDs, CLI (`trace`, `trace-analyze`, `replay`), replay for tests.
- **[CLI reference](guides/cli-reference.md)** — All `routekitai` commands and options.
- **[Providers](guides/providers.md)** — FakeModel, OpenAI, environment variables.

For design and concepts, see [Architecture](architecture.md). For security (PII redaction, tool filtering, approval gates), see [Security & Governance](security-and-governance.md).
