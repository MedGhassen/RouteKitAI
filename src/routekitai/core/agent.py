"""Agent primitive for RouteKit."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.hooks import ToolFilter
from routekitai.core.memory import Memory
from routekitai.core.message import Message
from routekitai.core.model import Model
from routekitai.core.policy import Policy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime
from routekitai.core.tool import Tool
from routekitai.graphs.graph import Graph
from routekitai.observability.trace import Trace, TraceEvent


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
    tool_filter: ToolFilter | None = Field(
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
                from routekitai.core.policies import ReActPolicy

                policy_adapter = PolicyAdapter(ReActPolicy(**self.policy))

        # Run via runtime
        return await self._runtime.run(self.name, prompt, policy=policy_adapter, **kwargs)

    async def run_stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        """Run the agent with streaming updates.

        Yields trace events and progress updates in real-time.

        Args:
            prompt: User prompt
            **kwargs: Additional run parameters

        Yields:
            Dicts with event information:
            - type: Event type (trace_event, progress_update, result)
            - data: Event data
            - result: Final RunResult (only in last event)

        Examples:
            >>> async for event in agent.run_stream("Hello"):
            ...     if event["type"] == "trace_event":
            ...         print(f"Event: {event['data']['type']}")
            ...     elif event["type"] == "progress_update":
            ...         print(f"Progress: {event['data']['progress_percent']}%")
        """
        # Use queues to collect events and progress updates
        trace_queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        result_queue: asyncio.Queue[RunResult] = asyncio.Queue()

        def trace_callback(event: TraceEvent) -> None:
            trace_queue.put_nowait(event)

        def progress_callback(progress: dict[str, Any]) -> None:
            progress_queue.put_nowait(progress)

        # Convert policy to PolicyAdapter if needed
        policy_adapter = None
        if self.policy:
            if isinstance(self.policy, Policy):
                policy_adapter = PolicyAdapter(self.policy)
            elif isinstance(self.policy, dict):
                from routekitai.core.policies import ReActPolicy

                policy_adapter = PolicyAdapter(ReActPolicy(**self.policy))

        # Add callbacks to runtime
        self._runtime.add_progress_callback(progress_callback)

        # Create a trace to capture events
        trace_id = str(uuid.uuid4())
        trace = Trace(trace_id=trace_id, metadata={"agent": self.name, "prompt": prompt})
        trace.add_event_callback(trace_callback)

        # Run agent in background task
        async def run_agent() -> None:
            try:
                result = await self._runtime.run(self.name, prompt, policy=policy_adapter, **kwargs)
                result_queue.put_nowait(result)
            except Exception as e:
                # Put error in result queue
                result_queue.put_nowait(None)  # type: ignore[arg-type]
                trace_queue.put_nowait(
                    TraceEvent(
                        type="error",
                        timestamp=asyncio.get_event_loop().time(),
                        data={"error": str(e), "error_type": type(e).__name__},
                    )
                )

        run_task = asyncio.create_task(run_agent())

        try:
            # Stream events as they arrive
            while True:
                # Check all queues with timeout
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(trace_queue.get()),
                        asyncio.create_task(progress_queue.get()),
                        asyncio.create_task(result_queue.get()),
                        run_task,
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.1,
                )

                if not done:
                    continue

                for task in done:
                    try:
                        result = await task
                        if task == run_task:
                            # Agent run completed
                            if result is not None:
                                # Type guard: result should be RunResult when task is run_task
                                from routekitai.core.agent import RunResult

                                assert isinstance(result, RunResult), (
                                    "Expected RunResult from run_task"
                                )
                                yield {
                                    "type": "result",
                                    "result": {
                                        "output": result.output.model_dump(mode="json"),
                                        "trace_id": result.trace_id,
                                        "final_state": result.final_state,
                                        "messages": [
                                            msg.model_dump(mode="json") for msg in result.messages
                                        ],
                                    },
                                }
                            return
                        elif isinstance(result, TraceEvent):
                            yield {
                                "type": "trace_event",
                                "data": {
                                    "type": result.type,
                                    "timestamp": result.timestamp,
                                    "data": result.data,
                                },
                            }
                        elif isinstance(result, dict):
                            yield {"type": "progress_update", "data": result}
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        pass

                # Cancel pending tasks
                for task in pending:
                    task.cancel()

        finally:
            # Clean up callbacks
            self._runtime.remove_progress_callback(progress_callback)
            if not run_task.done():
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass

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
            asyncio.get_running_loop()
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
                ) from None
        except RuntimeError:
            # No event loop exists, safe to use asyncio.run
            return asyncio.run(self.run(prompt, **kwargs))

    @classmethod
    def with_fake_model(
        cls,
        name: str,
        responses: list[str | dict[str, Any]],
        tools: list[Tool] | None = None,
    ) -> Agent:
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
        from routekitai.providers.local import FakeModel

        model = FakeModel(name=f"{name}_model")
        for response in responses:
            model.add_response(response)
        return cls(name=name, model=model, tools=tools or [])

    @classmethod
    def with_graph_policy(
        cls,
        name: str,
        graph: Graph,
        model: Model,
        runtime: Runtime | None = None,
        **kwargs: Any,
    ) -> Agent:
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
            >>> from routekitai.graphs import Graph, GraphNode, NodeType
            >>> graph = Graph(name="test", entry_node="start", nodes=[...])
            >>> agent = Agent.with_graph_policy("graph_agent", graph, model)
        """

        from routekitai.core.policies import GraphPolicy

        if runtime is None:
            runtime = Runtime(trace_dir=kwargs.get("trace_dir"))

        policy = GraphPolicy(graph=graph, runtime=runtime)
        return cls(name=name, model=model, policy=policy, **kwargs)
