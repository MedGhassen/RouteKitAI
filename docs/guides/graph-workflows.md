# Graph workflows

RouteKitAI lets you define agent workflows as **directed graphs**: nodes (model, tool, subgraph, condition) and edges that define control flow and state flow.

## Concepts

- **Graph** — Contains nodes, edges, an entry node, and an optional exit node. State is passed between nodes via **input_mapping** and **output_mapping**.
- **GraphNode** — A single step: `NodeType.MODEL` (run an agent), `NodeType.TOOL` (run a tool), `NodeType.SUBGRAPH` (run a nested graph), or `NodeType.CONDITION` (branch on state).
- **GraphEdge** — Connects two nodes (`source` → `target`). Optional `condition` label for conditional edges.
- **GraphPolicy** — Policy that executes a graph when the agent runs; use it with `Runtime` and registered agents.

## Defining a graph

```python
from routekitai.graphs import Graph, GraphNode, GraphEdge, NodeType

graph = Graph(
    name="my_workflow",
    entry_node="start",
    exit_node="end",
    nodes=[
        GraphNode(
            id="start",
            type=NodeType.MODEL,
            agent_name="writer",
            output_mapping={"output": "draft"},
        ),
        GraphNode(
            id="tool_step",
            type=NodeType.TOOL,
            tool_name="echo",
            input_mapping={"draft": "message"},
            output_mapping={"result": "echo_result"},
        ),
        GraphNode(
            id="end",
            type=NodeType.MODEL,
            agent_name="writer",
            input_mapping={"echo_result": "input"},
            output_mapping={"output": "final"},
        ),
    ],
    edges=[
        GraphEdge(source="start", target="tool_step"),
        GraphEdge(source="tool_step", target="end"),
    ],
)
```

- **input_mapping** — Maps graph state keys to this node’s inputs (e.g. `{"draft": "message"}` means the node receives `message = state["draft"]`).
- **output_mapping** — Maps this node’s outputs to graph state (e.g. `{"result": "echo_result"}` means `state["echo_result"] = node_output["result"]`).

## Using GraphPolicy

You need a **Runtime** with agents registered, then run with **GraphPolicy**:

```python
from pathlib import Path
from routekitai.core.runtime import Runtime
from routekitai.core.policies import GraphPolicy

runtime = Runtime(trace_dir=Path(".routekit/traces"))
runtime.register_agent(writer_agent)  # name must match agent_name in nodes

policy = GraphPolicy(graph=graph)
result = await runtime.run("writer", "Write a short greeting", policy=policy)
```

The agent name passed to `runtime.run()` is used as the default when nodes reference an `agent_name`; the graph’s MODEL nodes specify which agent runs at each step.

## Node types

| Type        | Use | Required fields |
|------------|-----|------------------|
| `MODEL`    | Run an agent | `agent_name` |
| `TOOL`     | Run a tool   | `tool_name`  |
| `SUBGRAPH` | Run a nested graph | `subgraph_name` |
| `CONDITION`| Branch on state | `condition` (callable taking state, returning next node id) |

## State flow

- Graph execution maintains a **state** dict. The entry node typically receives initial input (e.g. the user prompt) as part of state.
- Each node reads from state via **input_mapping** and writes back via **output_mapping**.
- Edges define which node runs next; for conditional edges, the **condition** on the edge or a **CONDITION** node determines the branch.

## Subgraphs

Use `NodeType.SUBGRAPH` and `subgraph_name` to call another graph as a step. The nested graph has its own entry/exit and state; you map parent state into the subgraph and map subgraph output back with input_mapping/output_mapping.

## Example: linear pipeline

Simple pipeline: model → tool → model:

```python
nodes = [
    GraphNode(id="a", type=NodeType.MODEL, agent_name="agent",
              output_mapping={"output": "x"}),
    GraphNode(id="b", type=NodeType.TOOL, tool_name="echo",
              input_mapping={"x": "message"}, output_mapping={"result": "y"}),
    GraphNode(id="c", type=NodeType.MODEL, agent_name="agent",
              input_mapping={"y": "input"}, output_mapping={"output": "final"}),
]
edges = [
    GraphEdge(source="a", target="b"),
    GraphEdge(source="b", target="c"),
]
graph = Graph(name="pipeline", entry_node="a", exit_node="c", nodes=nodes, edges=edges)
```

See the **examples** in the repo (e.g. `examples/graph_agent.py`, `examples/graph_policy.py`) for runnable graph workflows.
