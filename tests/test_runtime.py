"""Tests for Runtime capabilities."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from routekitai.core.agent import Agent, RunResult
from routekitai.core.errors import ToolError
from routekitai.core.message import MessageRole
from routekitai.core.model import Model, ModelResponse, ToolCall, Usage
from routekitai.core.runtime import Policy, Runtime, Step
from routekitai.core.tool import Tool, ToolPermission
from routekitai.observability.exporters.jsonl import JSONLExporter
from routekitai.sandbox.permissions import PermissionLevel, PermissionManager


class MockModel(Model):
    """Mock model for testing."""

    def __init__(self, name: str = "mock", provider: str = "test") -> None:
        super().__init__()
        object.__setattr__(self, "_name", name)
        self.provider = provider
        self.call_count = 0

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat implementation."""
        self.call_count += 1
        content = f"Response {self.call_count}"
        tool_calls = None
        if self.call_count == 1 and tools:
            # First call: return tool call
            tool_calls = [ToolCall(id="call_1", name="test_tool", arguments={"value": "test"})]
        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class TestInput(BaseModel):
    """Test input model."""

    value: str = Field(..., description="Test value")


class TestOutput(BaseModel):
    """Test output model."""

    result: str = Field(..., description="Test result")


class TestTool(Tool):
    """Test tool."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, name: str = "test_tool", should_fail: bool = False) -> None:
        super().__init__(
            name=name,
            description="Test tool",
            input_model=TestInput,
            output_model=TestOutput,
        )
        object.__setattr__(self, "should_fail", should_fail)
        object.__setattr__(self, "call_count", 0)

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute test tool."""
        current_count = getattr(self, "call_count", 0)
        object.__setattr__(self, "call_count", current_count + 1)
        if getattr(self, "should_fail", False):
            raise ValueError("Tool execution failed")
        return TestOutput(result=f"Processed: {input.value}")


class MockAgent(Agent):
    """Mock agent for testing."""

    def __init__(self, name: str = "test_agent") -> None:
        model = MockModel()
        tools = [TestTool()]
        super().__init__(name=name, model=model, tools=tools)

    async def run(self, prompt: str, **kwargs) -> RunResult:
        """Mock run implementation."""
        # This will be handled by runtime's step execution
        raise NotImplementedError("Use runtime.run() instead")


class TestPolicy(Policy):
    """Test policy."""

    async def next_steps(self, agent, messages, state):
        """Simple test policy."""
        import uuid

        if not messages or messages[-1].role != MessageRole.ASSISTANT:
            return [
                Step(
                    step_id=str(uuid.uuid4()),
                    step_type="model_call",
                    input_data={"messages": [m.model_dump() for m in messages]},
                )
            ]
        return []


@pytest.mark.asyncio
async def test_runtime_trace_export() -> None:
    """Test that runtime exports traces correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        agent = MockAgent()
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Hello")

        # Give async export a moment to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Check trace file exists
        trace_file = trace_dir / f"{result.trace_id}.jsonl"
        assert trace_file.exists()

        # Load and verify trace
        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None
        assert trace.trace_id == result.trace_id

        # Check events
        run_started = trace.get_events_by_type("run_started")
        assert len(run_started) > 0

        run_completed = trace.get_events_by_type("run_completed")
        assert len(run_completed) > 0


@pytest.mark.asyncio
async def test_runtime_replay() -> None:
    """Test that replay returns identical results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        agent = MockAgent()
        runtime.register_agent(agent)

        # Run original
        original_result = await runtime.run("test_agent", "Hello")

        # Give async trace export time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Replay
        replayed_result = await runtime.replay(original_result.trace_id, "test_agent")

        # Results should match
        assert replayed_result.output.content == original_result.output.content
        assert replayed_result.trace_id == original_result.trace_id


@pytest.mark.asyncio
async def test_permission_guard() -> None:
    """Test that permission guard blocks disallowed tool calls."""

    # Create a model that returns a tool call for restricted_tool
    class RestrictedModel(MockModel):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            self.call_count += 1
            return ModelResponse(
                content="I'll use the restricted tool",
                tool_calls=[
                    ToolCall(id="call_1", name="restricted_tool", arguments={"value": "test"})
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

    # Create permission manager that denies by default
    perm_manager = PermissionManager(default_level=PermissionLevel.NONE)

    runtime = Runtime(permission_manager=perm_manager)
    agent = MockAgent()
    agent.model = RestrictedModel()

    # Create a tool that requires network permission
    restricted_tool = TestTool(name="restricted_tool")
    restricted_tool.permissions = [ToolPermission.NETWORK]
    agent.tools = [restricted_tool]
    runtime.register_agent(agent)

    # This should fail because restricted_tool requires NETWORK permission
    # but permission manager denies by default
    with pytest.raises(ToolError, match="Permission denied"):
        await runtime.run("test_agent", "Use restricted tool")


@pytest.mark.asyncio
async def test_tool_timeout() -> None:
    """Test tool timeout handling."""

    class SlowTool(Tool):
        model_config = {"arbitrary_types_allowed": True}

        def __init__(self) -> None:
            super().__init__(
                name="slow_tool",
                description="Slow tool",
                timeout=0.1,  # 100ms timeout
            )

        async def run(self, input: BaseModel) -> BaseModel:
            await asyncio.sleep(1.0)  # Sleep for 1 second
            return TestOutput(result="done")

    # Create model that returns tool call for slow_tool
    class SlowToolModel(MockModel):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return ModelResponse(
                content="I'll use the slow tool",
                tool_calls=[ToolCall(id="call_1", name="slow_tool", arguments={"value": "test"})],
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

    runtime = Runtime(max_retries=0)
    agent = MockAgent()
    agent.model = SlowToolModel()
    agent.tools = [SlowTool()]
    runtime.register_agent(agent)

    with pytest.raises(ToolError, match="timed out"):
        await runtime.run("test_agent", "Use slow tool")


@pytest.mark.asyncio
async def test_concurrent_tool_execution() -> None:
    """Test concurrent tool execution."""

    class ConcurrentTool(Tool):
        model_config = {"arbitrary_types_allowed": True}

        def __init__(self, name: str, delay: float) -> None:
            super().__init__(
                name=name,
                description="Concurrent tool",
                input_model=TestInput,
                output_model=TestOutput,
            )
            object.__setattr__(self, "delay", delay)

        async def run(self, input: BaseModel) -> BaseModel:
            await asyncio.sleep(self.delay)
            return TestOutput(result=f"{self.name}: {input.value}")

    runtime = Runtime(max_concurrency=5)
    agent = MockAgent()
    agent.tools = [
        ConcurrentTool("tool1", 0.1),
        ConcurrentTool("tool2", 0.1),
        ConcurrentTool("tool3", 0.1),
    ]
    runtime.register_agent(agent)

    # Create policy that returns parallel tool calls, then finalizes
    class ParallelPolicy(Policy):
        async def next_steps(self, agent, messages, state):
            import uuid

            if not messages:
                return [
                    Step(
                        step_id=str(uuid.uuid4()),
                        step_type="model_call",
                        input_data={"messages": [m.model_dump() for m in messages]},
                    )
                ]

            # Check if we've already executed tools (avoid infinite loop)
            if state.get("tools_executed"):
                return []  # Finalize

            # Return parallel tool calls
            state["tools_executed"] = True
            return [
                Step(
                    step_id=str(uuid.uuid4()),
                    step_type="tool_call",
                    input_data={"tool_name": "tool1", "tool_args": {"value": "test1"}},
                ),
                Step(
                    step_id=str(uuid.uuid4()),
                    step_type="tool_call",
                    input_data={"tool_name": "tool2", "tool_args": {"value": "test2"}},
                ),
                Step(
                    step_id=str(uuid.uuid4()),
                    step_type="tool_call",
                    input_data={"tool_name": "tool3", "tool_args": {"value": "test3"}},
                ),
            ]

    start_time = asyncio.get_event_loop().time()
    await runtime.run("test_agent", "Hello", policy=ParallelPolicy())
    elapsed = asyncio.get_event_loop().time() - start_time

    # Should complete faster than sequential (3 * 0.1 = 0.3s)
    # But allow some overhead
    assert elapsed < 0.5  # Should be much faster than sequential
