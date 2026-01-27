"""Graph execution engine."""

from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.errors import RuntimeError as RouteKitRuntimeError
from routekitai.core.runtime import Runtime
from routekitai.graphs.graph import Graph, GraphNode, NodeType


class GraphExecutionState(BaseModel):
    """State during graph execution."""

    current_node: str | None = Field(default=None, description="Current node ID")
    visited_nodes: set[str] = Field(default_factory=set, description="Visited node IDs")
    state: dict[str, Any] = Field(default_factory=dict, description="Graph state data")
    execution_path: list[str] = Field(default_factory=list, description="Execution path (node IDs)")
    completed: bool = Field(default=False, description="Whether execution is complete")


class GraphExecutor(BaseModel):
    """Executes graph-based agent workflows deterministically.

    Graph execution is step-based and integrates with Runtime for tracing and replay.
    """

    runtime: Runtime = Field(..., description="Runtime for agent execution")
    graph: Graph = Field(..., description="Graph to execute")
    max_iterations: int = Field(default=100, description="Maximum execution iterations")

    async def execute(
        self, input_data: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Execute the graph with input data.

        Args:
            input_data: Initial input data for graph state
            **kwargs: Additional execution parameters

        Returns:
            Execution result with final output and full state

        Raises:
            RouteKitRuntimeError: If graph execution fails
        """
        # Validate graph
        errors = self.graph.validate_structure()
        if errors:
            raise RouteKitRuntimeError(f"Graph validation failed: {'; '.join(errors)}")

        # Check for cycles before execution
        cycle = self._detect_cycles()
        if cycle:
            raise RouteKitRuntimeError(
                f"Graph contains a cycle: {' -> '.join(cycle)}",
                context={"graph_name": self.graph.name},
            )

        # Validate entry node exists
        entry_node = self.graph.get_node(self.graph.entry_node)
        if not entry_node:
            raise RouteKitRuntimeError(
                f"Entry node '{self.graph.entry_node}' not found in graph '{self.graph.name}'",
                context={"graph_name": self.graph.name, "entry_node": self.graph.entry_node},
            )

        # Initialize execution state
        exec_state = GraphExecutionState(
            current_node=self.graph.entry_node,
            state=input_data or {},
        )

        iteration = 0
        while iteration < self.max_iterations:
            if exec_state.completed:
                break

            current_node_id = exec_state.current_node
            if not current_node_id:
                break

            # Get current node
            node = self.graph.get_node(current_node_id)
            if not node:
                raise RouteKitRuntimeError(
                    f"Node '{current_node_id}' not found in graph '{self.graph.name}'",
                    context={
                        "graph_name": self.graph.name,
                        "node_id": current_node_id,
                        "execution_path": exec_state.execution_path,
                        "iteration": iteration,
                    },
                )

            # Mark node as visited (track both set and path for different purposes)
            # Set is for cycle detection, path is for execution history
            exec_state.visited_nodes.add(current_node_id)
            exec_state.execution_path.append(current_node_id)

            # Detect if we're revisiting a node (potential infinite loop, even if not a cycle)
            if exec_state.execution_path.count(current_node_id) > 1:
                # Warn but don't fail - might be intentional for retry logic
                # Only fail if we've visited this node too many times
                visit_count = exec_state.execution_path.count(current_node_id)
                if visit_count > 10:  # Arbitrary threshold
                    raise RouteKitRuntimeError(
                        f"Node '{current_node_id}' visited {visit_count} times - possible infinite loop",
                        context={
                            "node_id": current_node_id,
                            "graph_name": self.graph.name,
                            "execution_path": exec_state.execution_path,
                            "visit_count": visit_count,
                        },
                    )

            # Execute node
            try:
                node_output = await self._execute_node(node, exec_state.state)
            except RouteKitRuntimeError:
                # Re-raise RouteKit errors as-is
                raise
            except Exception as e:
                # Wrap unknown exceptions
                raise RouteKitRuntimeError(
                    f"Node '{current_node_id}' execution failed: {e}",
                    context={
                        "node_id": current_node_id,
                        "node_type": node.type.value,
                        "graph_name": self.graph.name,
                    },
                ) from e

            # Update state with node output (safely merge, don't overwrite critical keys)
            if node.output_mapping:
                for output_key, state_key in node.output_mapping.items():
                    if output_key in node_output:
                        # Preserve existing state if key exists and is important
                        if state_key in exec_state.state and state_key.startswith("_"):
                            # Don't overwrite internal state keys
                            continue
                        exec_state.state[state_key] = node_output[output_key]
            else:
                # Default: merge all outputs into state, but preserve internal keys
                for key, value in node_output.items():
                    if not key.startswith("_"):  # Don't overwrite internal state
                        exec_state.state[key] = value

            # Determine next node(s)
            next_node = self._get_next_node(node, exec_state.state)
            if next_node:
                exec_state.current_node = next_node
            elif current_node_id == self.graph.exit_node:
                exec_state.completed = True
            else:
                # No more edges, execution complete
                exec_state.completed = True

            iteration += 1

        if iteration >= self.max_iterations:
            raise RouteKitRuntimeError(
                f"Graph execution exceeded max iterations ({self.max_iterations})"
            )

        return {
            "output": exec_state.state.get("output", exec_state.state),
            "state": exec_state.state,
            "execution_path": exec_state.execution_path,
            "visited_nodes": list(exec_state.visited_nodes),
        }

    async def _execute_node(self, node: GraphNode, state: dict[str, Any]) -> dict[str, Any]:
        """Execute a single graph node.

        Args:
            node: Node to execute
            state: Current graph state

        Returns:
            Node output data
        """
        # Prepare node inputs from state
        node_inputs = {}
        if node.input_mapping:
            for state_key, input_key in node.input_mapping.items():
                if state_key in state:
                    node_inputs[input_key] = state[state_key]
        else:
            # Default: pass all state as input, but filter out internal keys
            node_inputs = {k: v for k, v in state.items() if not k.startswith("_")}

        if node.type == NodeType.MODEL:
            return await self._execute_model_node(node, node_inputs)
        elif node.type == NodeType.TOOL:
            return await self._execute_tool_node(node, node_inputs)
        elif node.type == NodeType.SUBGRAPH:
            return await self._execute_subgraph_node(node, node_inputs)
        elif node.type == NodeType.CONDITION:
            return await self._execute_condition_node(node, node_inputs)
        else:
            raise RouteKitRuntimeError(f"Unknown node type: {node.type}")

    async def _execute_model_node(self, node: GraphNode, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a model/agent node.

        Args:
            node: Model node
            inputs: Node inputs

        Returns:
            Node output
        """
        if not node.agent_name:
            raise RouteKitRuntimeError(f"Node '{node.id}': MODEL type requires agent_name")

        if node.agent_name not in self.runtime.agents:
            raise RouteKitRuntimeError(f"Agent '{node.agent_name}' not found in runtime")

        # Extract prompt from inputs
        # Try common input keys, fallback to string representation
        prompt = inputs.get("prompt") or inputs.get("input") or inputs.get("text") or str(inputs)

        # Execute agent
        result = await self.runtime.run(node.agent_name, prompt)

        return {
            "output": result.output.content,
            "messages": [m.model_dump() for m in result.messages],
            "trace_id": result.trace_id,
        }

    async def _execute_tool_node(self, node: GraphNode, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool node.

        This method handles tool execution within a graph workflow. It:
        1. Locates the tool by name across all registered agents
        2. Maps graph state inputs to tool arguments using the tool's input model schema
        3. Executes the tool and converts the result to a format suitable for graph state

        The input mapping logic tries multiple strategies:
        - If inputs contain an "arguments" key, use it directly
        - If inputs contain a "message" key, use it for tools expecting a message parameter
        - If inputs contain an "output" key, use it as the message (common for echo tools)
        - Otherwise, match inputs to tool input model fields by name
        - As a fallback, use the first input value as the message

        Args:
            node: Tool node to execute
            inputs: Node inputs from graph state (may be transformed via input_mapping)

        Returns:
            Node output dictionary with "result" and "output" keys

        Raises:
            RouteKitRuntimeError: If tool is not found or execution fails
        """
        if not node.tool_name:
            raise RouteKitRuntimeError(f"Node '{node.id}': TOOL type requires tool_name")

        # Find tool in any agent
        tool = None
        for agent in self.runtime.agents.values():
            tool = next((t for t in agent.tools if t.name == node.tool_name), None)
            if tool:
                break

        if not tool:
            raise RouteKitRuntimeError(f"Tool '{node.tool_name}' not found")

        # Execute tool using execute() method which handles input validation
        # First, extract the actual tool arguments from inputs
        tool_args = {}

        if isinstance(inputs, dict):
            # Check for explicit arguments key
            if "arguments" in inputs and isinstance(inputs["arguments"], dict):
                tool_args = inputs["arguments"]
            else:
                # Try to match input model fields
                # For EchoTool, we need "message"
                if "message" in inputs:
                    tool_args = {"message": inputs["message"]}
                elif "output" in inputs:
                    # Previous node output - use as message for echo tool
                    tool_args = {"message": str(inputs["output"])}
                else:
                    # Try to use inputs directly, filtering out non-tool keys
                    # Get input model schema to see what fields are needed
                    if hasattr(tool, "input_model") and tool.input_model:
                        schema = tool.input_model.model_json_schema()
                        required_fields = schema.get("properties", {}).keys()
                        # Try to match inputs to required fields
                        for field in required_fields:
                            if field in inputs:
                                tool_args[field] = inputs[field]
                        # If no matches, use first value as message (common pattern)
                        if not tool_args and inputs:
                            first_value = list(inputs.values())[0]
                            tool_args = {"message": str(first_value)}
                    else:
                        tool_args = inputs
        else:
            tool_args = {"message": str(inputs)}

        # Execute tool
        result = await tool.execute(**tool_args)

        # Convert result to string if it's a Pydantic model
        if hasattr(result, "model_dump"):
            result_dict = result.model_dump()
            # Extract the actual result value (e.g., "echoed" for EchoTool)
            result = result_dict.get("echoed", result_dict.get("result", str(result)))
        elif hasattr(result, "dict"):
            result_dict = result.dict()
            result = result_dict.get("echoed", result_dict.get("result", str(result)))

        return {"result": result, "output": str(result)}

    async def _execute_subgraph_node(
        self, node: GraphNode, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a subgraph node.

        Args:
            node: Subgraph node
            inputs: Node inputs

        Returns:
            Node output

        Raises:
            RouteKitRuntimeError: If subgraph not found or execution fails
        """
        if not node.subgraph_name:
            raise RouteKitRuntimeError(f"Node '{node.id}': SUBGRAPH type requires subgraph_name")

        # Check if subgraph is registered in runtime's graph registry
        # For now, we'll look for a graph with the same name in the runtime's config
        graph_registry = self.runtime.config.get("graph_registry", {})

        if node.subgraph_name not in graph_registry:
            raise RouteKitRuntimeError(
                f"Subgraph '{node.subgraph_name}' not found in graph registry",
                context={"node_id": node.id, "subgraph_name": node.subgraph_name},
            )

        subgraph = graph_registry[node.subgraph_name]

        # Create a new executor for the subgraph
        subgraph_executor = GraphExecutor(
            runtime=self.runtime,
            graph=subgraph,
            max_iterations=self.max_iterations,
        )

        # Execute subgraph with inputs
        try:
            subgraph_result = await subgraph_executor.execute(input_data=inputs)
            # Return the subgraph's output
            return {
                "output": subgraph_result.get("output"),
                "state": subgraph_result.get("state", {}),
            }
        except Exception as e:
            raise RouteKitRuntimeError(
                f"Subgraph '{node.subgraph_name}' execution failed: {e}",
                context={"node_id": node.id, "subgraph_name": node.subgraph_name},
            ) from e

    async def _execute_condition_node(
        self, node: GraphNode, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a condition node.

        Args:
            node: Condition node
            inputs: Node inputs

        Returns:
            Node output with selected edge
        """
        if not node.condition:
            raise RouteKitRuntimeError(
                f"Node '{node.id}': CONDITION type requires condition function"
            )

        # Evaluate condition
        selected_edge = node.condition(inputs)

        return {"selected_edge": selected_edge, "condition_result": selected_edge}

    def _detect_cycles(self) -> list[str] | None:
        """Detect cycles in the graph using DFS.

        Returns:
            List of node IDs forming a cycle, or None if no cycle found
        """
        visited: set[str] = set()
        recursion_stack: set[str] = set()
        path: list[str] = []

        def dfs(node_id: str) -> list[str] | None:
            visited.add(node_id)
            recursion_stack.add(node_id)
            path.append(node_id)

            for edge in self.graph.get_outgoing_edges(node_id):
                if edge.target not in visited:
                    cycle = dfs(edge.target)
                    if cycle:
                        return cycle
                elif edge.target in recursion_stack:
                    # Cycle detected - find the cycle path
                    cycle_start_index = path.index(edge.target)
                    return path[cycle_start_index:] + [edge.target]

            path.pop()
            recursion_stack.remove(node_id)
            return None

        for node in self.graph.nodes:
            if node.id not in visited:
                cycle = dfs(node.id)
                if cycle:
                    return cycle
        return None

    def _get_next_node(self, node: GraphNode, state: dict[str, Any]) -> str | None:
        """Get the next node to execute based on outgoing edges.

        Args:
            node: Current node
            state: Current state

        Returns:
            Next node ID or None if no next node
        """
        outgoing_edges = self.graph.get_outgoing_edges(node.id)

        if not outgoing_edges:
            return None

        # If condition node, use condition result
        if node.type == NodeType.CONDITION:
            selected_edge = state.get("selected_edge")
            if selected_edge:
                # Find edge with matching condition label
                for edge in outgoing_edges:
                    if edge.condition == selected_edge:
                        return edge.target
                # Fallback: use first edge
                return outgoing_edges[0].target
            return outgoing_edges[0].target if outgoing_edges else None

        # For other nodes, use first outgoing edge (can be extended for parallel execution)
        return outgoing_edges[0].target if outgoing_edges else None
