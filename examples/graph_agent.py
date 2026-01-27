"""Example: Graph-based agent orchestration."""

import asyncio
from pathlib import Path
from typing import Any

from routekitai.core.agent import Agent, RunResult
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.graphs.executors import GraphExecutor
from routekitai.graphs.graph import Graph, GraphEdge, GraphNode, NodeType
from routekitai.providers.local import FakeModel


class GraphAgent(Agent):
    """Agent for graph execution example."""

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        raise NotImplementedError("Use graph executor instead")


async def main() -> None:
    """Run graph orchestration example."""
    print("Running graph orchestration example...")

    # Create models
    model1 = FakeModel(name="model1")
    model1.add_response("I'll process this and use the echo tool.")
    model1.add_response(
        {
            "content": "Calling echo",
            "tool_calls": [
                {"id": "call_1", "name": "echo", "arguments": {"message": "Hello from graph"}}
            ],
        }
    )
    model1.add_response("Echo completed successfully")

    model2 = FakeModel(name="model2")
    model2.add_response("Finalizing the result: Graph execution complete")

    # Create agents
    agent1 = GraphAgent(name="agent1", model=model1, tools=[EchoTool()])
    agent2 = GraphAgent(name="agent2", model=model2, tools=[])

    # Create runtime
    trace_dir = Path(".routekit") / "traces"
    runtime = Runtime(trace_dir=trace_dir)
    runtime.register_agent(agent1)
    runtime.register_agent(agent2)

    # Define graph: agent1 -> tool -> agent2
    graph = Graph(
        name="example_graph",
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
                input_mapping={"agent1_result": "arguments"},
                output_mapping={"result": "echo_result"},
            ),
            GraphNode(
                id="end",
                type=NodeType.MODEL,
                agent_name="agent2",
                input_mapping={"echo_result": "prompt"},
                output_mapping={"output": "final_output"},
            ),
        ],
        edges=[
            GraphEdge(source="start", target="echo_tool"),
            GraphEdge(source="echo_tool", target="end"),
        ],
    )

    # Create executor
    executor = GraphExecutor(runtime=runtime, graph=graph)

    # Execute graph
    result = await executor.execute(input_data={"input": "Process this task"})

    print("\nGraph execution result:")
    print(f"  Final output: {result['output']}")
    print(f"  Execution path: {' -> '.join(result['execution_path'])}")
    print(f"  Visited nodes: {result['visited_nodes']}")
    print(f"  Full state: {result['state']}")


if __name__ == "__main__":
    asyncio.run(main())
