"""Example: Graph-based agent orchestration with OpenAI.

This example demonstrates how to create a graph-based agent workflow using OpenAI models.
The graph orchestrates multiple agents and tools in a sequential workflow.

To run this example:
1. Set your OpenAI API key: export OPENAI_API_KEY='your-api-key-here'
2. Run: python examples/graph_agent_real.py

Note: This example uses real OpenAI API calls and will consume API credits.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from routekitai.core.agent import Agent, RunResult
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.graphs.executors import GraphExecutor
from routekitai.graphs.graph import Graph, GraphEdge, GraphNode, NodeType
from routekitai.providers.openai import OpenAIChatModel


class GraphAgent(Agent):
    """Agent for graph execution example.

    This agent can be used both:
    1. Directly via agent.run() - uses default ReAct policy
    2. Through graph executor - uses runtime.run() which respects graph orchestration
    """

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        """Run the agent with a prompt.

        This implementation allows the agent to work independently or within a graph.
        When called directly, it uses the agent's default policy (ReAct if none specified).
        When called through graph executor, the runtime handles the execution.

        Args:
            prompt: User prompt
            **kwargs: Additional run parameters (policy, etc.)

        Returns:
            RunResult with output, trace_id, final_state, and messages
        """
        # Use the base class implementation which handles runtime execution
        # This allows the agent to work both standalone and within graphs
        return await super().run(prompt, **kwargs)


async def main() -> None:
    """Run graph orchestration example with OpenAI."""
    print("Running graph orchestration example with OpenAI...")
    print("=" * 60)

    # Get API key from environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. "
            "Please set it with: export OPENAI_API_KEY='your-api-key-here'"
        )

    print("✓ Using OpenAI API (model: gpt-4o-mini)")
    print()

    # Create OpenAI models
    # Using gpt-4o-mini for cost efficiency, but you can use gpt-4, gpt-3.5-turbo, etc.
    model1 = OpenAIChatModel(
        name="gpt-4o-mini",
        api_key=api_key,
        provider="openai",
    )

    model2 = OpenAIChatModel(
        name="gpt-4o-mini",
        api_key=api_key,
        provider="openai",
    )

    # Create agents
    # Agent 1: Processes the input and decides to use the echo tool
    agent1 = GraphAgent(name="agent1", model=model1, tools=[EchoTool()])

    # Agent 2: Finalizes the result based on the tool output
    agent2 = GraphAgent(name="agent2", model=model2, tools=[])

    # Create runtime with tracing
    trace_dir = Path(".routekit") / "traces"
    runtime = Runtime(trace_dir=trace_dir)
    runtime.register_agent(agent1)
    runtime.register_agent(agent2)

    print("✓ Created agents and runtime")
    print()

    # Define graph workflow: agent1 -> tool -> agent2
    # This creates a pipeline where:
    # 1. Agent1 processes the input
    # 2. Echo tool is called with agent1's output
    # 3. Agent2 processes the tool result and produces final output
    graph = Graph(
        name="openai_graph_example",
        entry_node="start",
        exit_node="end",
        nodes=[
            GraphNode(
                id="start",
                type=NodeType.MODEL,
                agent_name="agent1",
                # Map state["input"] to node_inputs["prompt"]
                input_mapping={"input": "prompt"},
                # Map node output["output"] to state["agent1_result"]
                output_mapping={"output": "agent1_result"},
            ),
            GraphNode(
                id="echo_tool",
                type=NodeType.TOOL,
                tool_name="echo",
                # Map state["agent1_result"] (string content) to node_inputs["message"]
                input_mapping={"agent1_result": "message"},
                # Map tool result to state["echo_result"]
                # The tool returns {"result": "...", "output": "..."}, we extract "result"
                output_mapping={"result": "echo_result"},
            ),
            GraphNode(
                id="end",
                type=NodeType.MODEL,
                agent_name="agent2",
                # Map state["echo_result"] (string from tool) to node_inputs["prompt"]
                input_mapping={"echo_result": "prompt"},
                # Map final output to state["final_output"]
                output_mapping={"output": "final_output"},
            ),
        ],
        edges=[
            GraphEdge(source="start", target="echo_tool"),
            GraphEdge(source="echo_tool", target="end"),
        ],
    )

    print("✓ Defined graph workflow:")
    print("  start (agent1) -> echo_tool -> end (agent2)")
    print()

    # Create executor
    executor = GraphExecutor(runtime=runtime, graph=graph)

    # Execute graph with a real task
    print("Executing graph with input: 'Create a summary of routkitai framework'")
    print("-" * 60)
    result = await executor.execute(input_data={"input": "Create a summary of routkitai framework"})

    print()
    print("=" * 60)
    print("Graph execution completed!")
    print("=" * 60)

    # Extract final output from state (output_mapping puts it there)
    state = result.get("state", {})
    final_output = state.get("final_output") or state.get("output") or result.get("output")

    if final_output:
        print("\nFinal output:")
        print("-" * 60)
        # Handle both string and dict outputs
        if isinstance(final_output, dict):
            print(final_output.get("content", final_output.get("output", str(final_output))))
        else:
            print(str(final_output))
    else:
        print("\nFinal output: N/A")
        print(f"\nFull state keys: {list(state.keys())}")
        print(f"Result keys: {list(result.keys())}")

    print(f"\nExecution path: {' -> '.join(result.get('execution_path', []))}")
    print(f"Visited nodes: {result.get('visited_nodes', [])}")

    # Show intermediate results for debugging
    if state.get("agent1_result"):
        print(f"\nAgent1 result (first 100 chars): {str(state.get('agent1_result'))[:100]}...")
    if state.get("echo_result"):
        print(f"Echo result (first 100 chars): {str(state.get('echo_result'))[:100]}...")

    # Show trace information
    if trace_dir.exists():
        trace_files = list(trace_dir.glob("*.jsonl"))
        if trace_files:
            latest_trace = max(trace_files, key=lambda p: p.stat().st_mtime)
            print(f"\nTrace saved to: {latest_trace}")


if __name__ == "__main__":
    asyncio.run(main())
