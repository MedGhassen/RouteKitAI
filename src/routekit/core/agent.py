"""Agent primitive for RouteKit."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from routekit.core.errors import PolicyError
from routekit.core.memory import Memory
from routekit.core.message import Message
from routekit.core.model import Model
from routekit.core.policy import Policy
from routekit.core.policy_adapter import PolicyAdapter
from routekit.core.runtime import Runtime
from routekit.core.tool import Tool

if TYPE_CHECKING:
    from routekit.core.hooks import ToolFilter
    from routekit.graphs.graph import Graph


class RunResult(BaseModel):
    """Result of an agent run."""

    output: Message = Field(..., description="Final output message")
    trace_id: str = Field(..., description="Trace ID for this run")
    final_state: dict[str, Any] = Field(default_factory=dict, description="Final agent state")
    messages: list[Message] = Field(default_factory=list, description="All messages in the run")


class Agent(BaseModel):
    """Agent with model, tools, policy, and memory.

    Provides a clean API for creating and running agents.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(..., description="Agent name")
    model: Model = Field(..., description="Model used by the agent")
    tools: list[Tool] = Field(default_factory=list, description="Tools available to the agent")
    policy: Policy | dict[str, Any] | None = Field(
        default=None, description="Agent policy or policy configuration"
    )
    memory: Memory | None = Field(default=None, description="Agent memory system")
    tool_filter: "ToolFilter | None" = Field(
        default=None, description="Agent-level tool allow/deny list"
    )
    trace_dir: Path | None = Field(default=None, description="Directory for trace files")

    def __init__(self, **data: Any) -> None:
        """Initialize agent with optional runtime."""
        super().__init__(**data)
        # Create internal runtime if not provided
        if not hasattr(self, "_runtime"):
            trace_dir = data.get("trace_dir")
            if trace_dir is None:
                trace_dir = Path(".routekit") / "traces"
            self._runtime = Runtime(trace_dir=trace_dir)
            self._runtime.register_agent(self)

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        """Run the agent with a prompt.

        Args:
            prompt: User prompt
            **kwargs: Additional run parameters

        Returns:
            RunResult with output, trace_id, final_state, and messages

        Raises:
            PolicyError: If agent policy fails
        """
        # Convert policy to PolicyAdapter if needed
        policy_adapter = None
        if self.policy:
            if isinstance(self.policy, Policy):
                policy_adapter = PolicyAdapter(self.policy)
            elif isinstance(self.policy, dict):
                # Legacy dict-based policy config - convert to appropriate policy
                from routekit.core.policies import ReActPolicy

                policy_adapter = PolicyAdapter(ReActPolicy(**self.policy))

        # Run via runtime
        return await self._runtime.run(self.name, prompt, policy=policy_adapter, **kwargs)

    def run_sync(self, prompt: str, **kwargs: Any) -> RunResult:
        """Synchronous wrapper for agent.run().

        Args:
            prompt: User prompt
            **kwargs: Additional run parameters

        Returns:
            RunResult with output, trace_id, final_state, and messages

        Raises:
            RuntimeError: If called from within an async context
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - need to use a different approach
            # Try to use nest_asyncio if available, otherwise raise error
            try:
                import nest_asyncio

                nest_asyncio.apply()
                return asyncio.run(self.run(prompt, **kwargs))
            except ImportError:
                raise RuntimeError(
                    "Cannot use run_sync() in an async context. "
                    "Either use 'await agent.run()' or install nest_asyncio: pip install nest-asyncio"
                )
        except RuntimeError:
            # No event loop exists, safe to use asyncio.run
            return asyncio.run(self.run(prompt, **kwargs))

    @classmethod
    def with_fake_model(
        cls,
        name: str,
        responses: list[str | dict[str, Any]],
        tools: list[Tool] | None = None,
    ) -> "Agent":
        """Create agent with FakeModel for testing.

        Args:
            name: Agent name
            responses: List of responses to queue in FakeModel
            tools: Optional list of tools

        Returns:
            Agent instance with FakeModel

        Examples:
            >>> agent = Agent.with_fake_model("test", ["Hello!", "World!"])
            >>> result = await agent.run("Hi")
        """
        from routekit.providers.local import FakeModel

        model = FakeModel(name=f"{name}_model")
        for response in responses:
            model.add_response(response)
        return cls(name=name, model=model, tools=tools or [])

    @classmethod
    def with_graph_policy(
        cls,
        name: str,
        graph: "Graph",
        model: Model,
        runtime: Runtime | None = None,
        **kwargs: Any,
    ) -> "Agent":
        """Create agent with graph policy.

        Args:
            name: Agent name
            graph: Graph to execute
            model: Model instance
            runtime: Optional runtime (will create one if not provided)
            **kwargs: Additional agent parameters

        Returns:
            Agent instance with GraphPolicy

        Examples:
            >>> from routekit.graphs import Graph, GraphNode, NodeType
            >>> graph = Graph(name="test", entry_node="start", nodes=[...])
            >>> agent = Agent.with_graph_policy("graph_agent", graph, model)
        """
        if TYPE_CHECKING:
            from routekit.graphs.graph import Graph

        from routekit.core.policies import GraphPolicy

        if runtime is None:
            runtime = Runtime(trace_dir=kwargs.get("trace_dir"))

        policy = GraphPolicy(graph=graph, runtime=runtime)
        return cls(name=name, model=model, policy=policy, **kwargs)
