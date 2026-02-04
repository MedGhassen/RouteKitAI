"""Graph definition for agent orchestration."""

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    """Type of graph node."""

    MODEL = "model"  # Execute a model call
    TOOL = "tool"  # Execute a tool
    SUBGRAPH = "subgraph"  # Execute a nested graph
    CONDITION = "condition"  # Conditional branching


class GraphNode(BaseModel):
    """Node in an agent orchestration graph.

    Nodes represent execution units in the graph. They can be:
    - Model nodes: Execute a model/agent
    - Tool nodes: Execute a tool
    - Subgraph nodes: Execute a nested graph
    - Condition nodes: Branch based on state
    """

    id: str = Field(..., description="Unique node ID")
    type: NodeType = Field(..., description="Node type")
    agent_name: str | None = Field(default=None, description="Agent name (for MODEL nodes)")
    tool_name: str | None = Field(default=None, description="Tool name (for TOOL nodes)")
    subgraph_name: str | None = Field(
        default=None, description="Subgraph name (for SUBGRAPH nodes)"
    )
    condition: Callable[[dict[str, Any]], str] | None = Field(
        default=None, description="Condition function for CONDITION nodes (returns edge ID)"
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    input_mapping: dict[str, str] = Field(
        default_factory=dict, description="Map graph state keys to node inputs"
    )
    output_mapping: dict[str, str] = Field(
        default_factory=dict, description="Map node outputs to graph state keys"
    )


class GraphEdge(BaseModel):
    """Edge connecting nodes in a graph."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    condition: str | None = Field(
        default=None, description="Optional condition label for conditional edges"
    )


class Graph(BaseModel):
    """Graph-based orchestration workflow.

    Graphs define explicit control flow between nodes, enabling:
    - Sequential execution
    - Parallel execution
    - Conditional branching
    - Nested subgraphs
    """

    name: str = Field(..., description="Graph name")
    nodes: list[GraphNode] = Field(default_factory=list, description="Graph nodes")
    edges: list[GraphEdge] = Field(default_factory=list, description="Graph edges")
    entry_node: str = Field(..., description="Entry node ID")
    exit_node: str | None = Field(default=None, description="Exit node ID (optional)")
    state_schema: dict[str, Any] = Field(default_factory=dict, description="Schema for graph state")
    config: dict[str, Any] = Field(default_factory=dict, description="Graph configuration")

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get a node by ID.

        Args:
            node_id: Node ID

        Returns:
            GraphNode or None if not found
        """
        return next((n for n in self.nodes if n.id == node_id), None)

    def get_outgoing_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all outgoing edges from a node.

        Args:
            node_id: Source node ID

        Returns:
            List of outgoing edges
        """
        return [e for e in self.edges if e.source == node_id]

    def get_incoming_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all incoming edges to a node.

        Args:
            node_id: Target node ID

        Returns:
            List of incoming edges
        """
        return [e for e in self.edges if e.target == node_id]

    def validate_structure(self) -> list[str]:
        """Validate graph structure.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check entry node exists
        if not self.get_node(self.entry_node):
            errors.append(f"Entry node '{self.entry_node}' not found")

        # Check exit node exists (if specified)
        if self.exit_node and not self.get_node(self.exit_node):
            errors.append(f"Exit node '{self.exit_node}' not found")

        # Check all edges reference valid nodes
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in node_ids:
                errors.append(f"Edge target '{edge.target}' not found")

        # Check node types match their configuration
        for node in self.nodes:
            if node.type == NodeType.MODEL and not node.agent_name:
                errors.append(f"Node '{node.id}': MODEL type requires agent_name")
            elif node.type == NodeType.TOOL and not node.tool_name:
                errors.append(f"Node '{node.id}': TOOL type requires tool_name")
            elif node.type == NodeType.SUBGRAPH and not node.subgraph_name:
                errors.append(f"Node '{node.id}': SUBGRAPH type requires subgraph_name")
            elif node.type == NodeType.CONDITION and not node.condition:
                errors.append(f"Node '{node.id}': CONDITION type requires condition function")

        # Check for unreachable nodes (nodes with no incoming edges except entry node)
        if self.nodes:
            reachable_nodes = {self.entry_node}
            # BFS from entry node to find all reachable nodes
            queue = [self.entry_node]
            while queue:
                current = queue.pop(0)
                for edge in self.get_outgoing_edges(current):
                    if edge.target not in reachable_nodes:
                        reachable_nodes.add(edge.target)
                        queue.append(edge.target)

            # Check for unreachable nodes (warn, but don't error - might be intentional)
            all_node_ids = {n.id for n in self.nodes}
            unreachable = all_node_ids - reachable_nodes
            if unreachable and self.exit_node:
                # Only warn if exit node is unreachable, otherwise it's just unused nodes
                if self.exit_node in unreachable:
                    errors.append(f"Exit node '{self.exit_node}' is unreachable from entry node")

        return errors
