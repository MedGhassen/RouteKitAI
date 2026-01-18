"""Tests for subgraph execution."""

import pytest

from routekit.core.agent import Agent
from routekit.core.runtime import Runtime
from routekit.graphs.executors import GraphExecutor
from routekit.graphs.graph import Graph, GraphEdge, GraphNode, NodeType
from routekit.providers.local import FakeModel


class SubgraphTestAgent(Agent):
    """Test agent for subgraph execution."""
    
    async def run(self, prompt: str, **kwargs):
        raise NotImplementedError("Use graph executor instead")


@pytest.mark.asyncio
async def test_subgraph_execution() -> None:
    """Test subgraph node execution."""
    model = FakeModel(name="test")
    model.add_response("Subgraph result")
    
    agent = SubgraphTestAgent(name="test_agent", model=model, tools=[])
    
    runtime = Runtime()
    runtime.register_agent(agent)
    
    # Create a subgraph
    subgraph = Graph(
        name="subgraph",
        entry_node="sub_start",
        nodes=[
            GraphNode(id="sub_start", type=NodeType.MODEL, agent_name="test_agent"),
        ],
        edges=[],
    )
    
    # Register subgraph in runtime config
    runtime.config["graph_registry"] = {"subgraph": subgraph}
    
    # Create main graph with subgraph node
    main_graph = Graph(
        name="main_graph",
        entry_node="start",
        nodes=[
            GraphNode(id="start", type=NodeType.SUBGRAPH, subgraph_name="subgraph"),
        ],
        edges=[],
    )
    
    executor = GraphExecutor(runtime=runtime, graph=main_graph)
    result = await executor.execute(input_data={"input": "test"})
    
    assert "output" in result
    # The subgraph node "start" should be in the execution path
    assert "start" in result["execution_path"]
    # The subgraph should have executed and produced output
    assert result["output"] is not None


@pytest.mark.asyncio
async def test_subgraph_not_found() -> None:
    """Test error when subgraph not found."""
    model = FakeModel(name="test")
    agent = SubgraphTestAgent(name="test_agent", model=model, tools=[])
    
    runtime = Runtime()
    runtime.register_agent(agent)
    
    graph = Graph(
        name="main_graph",
        entry_node="start",
        nodes=[
            GraphNode(id="start", type=NodeType.SUBGRAPH, subgraph_name="nonexistent"),
        ],
        edges=[],
    )
    
    executor = GraphExecutor(runtime=runtime, graph=graph)
    
    from routekit.core.errors import RuntimeError as RouteKitRuntimeError
    with pytest.raises(RouteKitRuntimeError, match="not found in graph registry"):
        await executor.execute()
