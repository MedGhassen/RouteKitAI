"""Example: Graph Policy — run a graph workflow via the policy adapter."""

import asyncio
from pathlib import Path
from typing import Any

from routekitai.core.agent import Agent, RunResult
from routekitai.core.policies import GraphPolicy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.graphs.graph import Graph, GraphEdge, GraphNode, NodeType
from routekitai.providers.local import FakeModel


class GraphPolicyAgent(Agent):
    """Agent for graph policy example (execution is via graph, not agent.run())."""

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        raise NotImplementedError("Use runtime.run() with GraphPolicy instead")


async def main() -> None:
    """Run graph policy example: user prompt -> graph (agent1 -> echo -> agent2) -> result."""
    trace_dir = Path(".routekit") / "traces"
    runtime = Runtime(trace_dir=trace_dir)

    # Agent1: processes input and produces content (no tool calls in this graph flow)
    model1 = FakeModel(
        name="model1",
        responses={"execute": "Processed the request.", "graph": "Processed the request."},
    )

    # Agent2: finalizes with a clear completion message
    model2 = FakeModel(
        name="model2",
        responses={
            "processed": "Graph execution complete.",
            "request": "Graph execution complete.",
        },
    )

    agent1 = GraphPolicyAgent(name="agent1", model=model1, tools=[EchoTool()])
    agent2 = GraphPolicyAgent(name="agent2", model=model2, tools=[])

    runtime.register_agent(agent1)
    runtime.register_agent(agent2)

    # Graph: start (agent1) -> echo_tool -> end (agent2)
    graph = Graph(
        name="graph_policy_example",
        entry_node="start",
        exit_node="end",
        nodes=[
            GraphNode(
                id="start",
                type=NodeType.MODEL,
                agent_name="agent1",
                input_mapping={"prompt": "input"},
                output_mapping={"output": "agent1_result"},
            ),
            GraphNode(
                id="echo_tool",
                type=NodeType.TOOL,
                tool_name="echo",
                input_mapping={"agent1_result": "message"},
                output_mapping={"result": "echo_result"},
            ),
            GraphNode(
                id="end",
                type=NodeType.MODEL,
                agent_name="agent2",
                input_mapping={"echo_result": "prompt"},
                output_mapping={"output": "final_output"},  # policy reads state["final_output"]
            ),
        ],
        edges=[
            GraphEdge(source="start", target="echo_tool"),
            GraphEdge(source="echo_tool", target="end"),
        ],
    )

    graph_policy = GraphPolicy(graph=graph, runtime=runtime)
    policy = PolicyAdapter(graph_policy)

    prompt = "Execute a graph workflow"
    result = await runtime.run(
        "agent1",  # entry agent name; policy runs the graph
        prompt,
        policy=policy,
    )

    # Show steps and outcome of each (from last graph run)
    graph_result = getattr(runtime, "_last_graph_result", None)
    if graph_result:
        state = graph_result.get("state", {})
        execution_path = graph_result.get("execution_path", [])
        # Map each node to the state key it writes (from output_mapping)
        node_to_state_key = {}
        for node in graph.nodes:
            for _out_key, state_key in node.output_mapping.items():
                node_to_state_key[node.id] = state_key
                break
        print("Steps:")
        print(f"  0. input: {prompt!r}")
        for i, node_id in enumerate(execution_path, start=1):
            state_key = node_to_state_key.get(node_id)
            outcome = state.get(state_key, state.get(node_id, "—"))
            if isinstance(outcome, dict):
                outcome = outcome.get("output", outcome.get("result", str(outcome)))
            print(f"  {i}. {node_id}: {outcome}")
        print()

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
