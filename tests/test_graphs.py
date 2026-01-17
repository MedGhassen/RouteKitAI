"""Tests for graph orchestration."""

import pytest

from routekit.core.agent import Agent, RunResult
from routekit.core.runtime import Runtime
from routekit.core.tools import EchoTool
from routekit.graphs.executors import GraphExecutor
from routekit.graphs.graph import Graph, GraphEdge, GraphNode, NodeType
from routekit.providers.local import FakeModel


class TestAgent(Agent):
    """Test agent for graph execution."""

    async def run(self, prompt: str, **kwargs) -> RunResult:
        raise NotImplementedError("Use graph executor instead")


@pytest.mark.asyncio
async def test_graph_execution_deterministic() -> None:
    """Test that graph execution is deterministic."""
    model = FakeModel(name="test")
    model.add_response("Response 1")
    model.add_response("Response 2")

    agent = TestAgent(name="test_agent", model=model, tools=[])

    runtime = Runtime()
    runtime.register_agent(agent)

    graph = Graph(
        name="simple_graph",
        entry_node="node1",
        exit_node="node2",
        nodes=[
            GraphNode(id="node1", type=NodeType.MODEL, agent_name="test_agent"),
            GraphNode(id="node2", type=NodeType.MODEL, agent_name="test_agent"),
        ],
        edges=[GraphEdge(source="node1", target="node2")],
    )

    executor = GraphExecutor(runtime=runtime, graph=graph)

    # Execute twice - should be deterministic
    result1 = await executor.execute(input_data={"input": "test"})
    result2 = await executor.execute(input_data={"input": "test"})

    assert result1["execution_path"] == result2["execution_path"]
    assert result1["visited_nodes"] == result2["visited_nodes"]


@pytest.mark.asyncio
async def test_graph_with_tool() -> None:
    """Test graph execution with tool node."""
    model = FakeModel(name="test")
    model.add_response({"content": "Calling echo", "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {"message": "test"}}]})
    model.add_response("Echo completed")

    agent = TestAgent(name="test_agent", model=model, tools=[EchoTool()])

    runtime = Runtime()
    runtime.register_agent(agent)

    graph = Graph(
        name="tool_graph",
        entry_node="start",
        nodes=[
            GraphNode(id="start", type=NodeType.MODEL, agent_name="test_agent"),
            GraphNode(id="echo", type=NodeType.TOOL, tool_name="echo"),
        ],
        edges=[GraphEdge(source="start", target="echo")],
    )

    executor = GraphExecutor(runtime=runtime, graph=graph)

    result = await executor.execute()

    assert "echo" in result["execution_path"]
    assert "start" in result["execution_path"]


@pytest.mark.asyncio
async def test_graph_validation() -> None:
    """Test graph validation."""
    # Valid graph
    graph = Graph(
        name="valid",
        entry_node="node1",
        nodes=[GraphNode(id="node1", type=NodeType.MODEL, agent_name="agent1")],
        edges=[],
    )

    errors = graph.validate()
    assert len(errors) == 0

    # Invalid graph - missing entry node
    graph2 = Graph(
        name="invalid",
        entry_node="missing",
        nodes=[GraphNode(id="node1", type=NodeType.MODEL, agent_name="agent1")],
        edges=[],
    )

    errors = graph2.validate()
    assert len(errors) > 0
    assert any("missing" in error.lower() for error in errors)


@pytest.mark.asyncio
async def test_graph_state_mapping() -> None:
    """Test graph state input/output mapping."""
    model = FakeModel(name="test")
    model.add_response("Processed: test_input")

    agent = TestAgent(name="test_agent", model=model, tools=[])

    runtime = Runtime()
    runtime.register_agent(agent)

    graph = Graph(
        name="mapping_graph",
        entry_node="process",
        nodes=[
            GraphNode(
                id="process",
                type=NodeType.MODEL,
                agent_name="test_agent",
                input_mapping={"input_data": "prompt"},
                output_mapping={"output": "result"},
            ),
        ],
        edges=[],
    )

    executor = GraphExecutor(runtime=runtime, graph=graph)

    result = await executor.execute(input_data={"input_data": "test_input"})

    assert "result" in result["state"]
    assert "test_input" in result["state"]["result"] or "Processed" in result["state"]["result"]
