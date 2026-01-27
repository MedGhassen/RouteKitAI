"""Integration tests for end-to-end RouteKit functionality."""

import tempfile
from pathlib import Path

import pytest

from routekitai.core.agent import Agent
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.providers.local import FakeModel


class TestAgent(Agent):
    """Concrete agent implementation for testing."""

    async def run(self, prompt: str, **kwargs):
        """Not used - runtime handles execution."""
        raise NotImplementedError("Use runtime.run() instead")


@pytest.mark.asyncio
async def test_end_to_end_with_echo_tool() -> None:
    """Test full agent loop with EchoTool."""

    # Create fake model that returns tool call
    def response_fn(messages, tools):
        """Return response with tool call."""
        last_msg = messages[-1] if messages else None
        if last_msg and "echo" in last_msg.content.lower():
            return {
                "content": "I'll echo that for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "echo",
                        "arguments": {"message": "Hello RouteKit!"},
                    }
                ],
            }
        return "How can I help you?"

    model = FakeModel(name="test", response_fn=response_fn)
    agent = TestAgent(name="test_agent", model=model, tools=[EchoTool()])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        # Run agent
        result = await runtime.run("test_agent", "Please echo 'Hello RouteKit!'")

        # Verify result
        assert result.output is not None
        assert result.trace_id is not None
        assert len(result.messages) > 0

        # Verify trace file exists (give async export a moment to complete)
        import asyncio

        await asyncio.sleep(0.1)  # Small delay for async export
        trace_file = trace_dir / f"{result.trace_id}.jsonl"
        assert trace_file.exists(), f"Trace file should exist at {trace_file}"

        # Verify tool was called
        tool_messages = [m for m in result.messages if m.role.value == "tool"]
        assert len(tool_messages) > 0, "Tool should have been called"


@pytest.mark.asyncio
async def test_react_policy_default() -> None:
    """Test that ReActPolicy is used by default."""
    model = FakeModel(
        name="test",
        responses={
            "hello": {
                "content": "I'll use the echo tool.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "echo",
                        "arguments": {"message": "test"},
                    }
                ],
            },
        },
    )

    agent = TestAgent(name="test_agent", model=model, tools=[EchoTool()])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        # Run without specifying policy (should use ReActPolicy)
        result = await runtime.run("test_agent", "hello")

        # Should complete successfully
        assert result.output is not None
        assert result.trace_id is not None


@pytest.mark.asyncio
async def test_trace_export_on_every_run() -> None:
    """Test that every run produces a trace file."""
    model = FakeModel(name="test")
    agent = TestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        # Run multiple times
        trace_ids = []
        for i in range(3):
            result = await runtime.run("test_agent", f"test {i}")
            trace_ids.append(result.trace_id)

        # Give async export tasks time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Verify all trace files exist
        for trace_id in trace_ids:
            trace_file = trace_dir / f"{trace_id}.jsonl"
            assert trace_file.exists(), f"Trace file should exist for {trace_id}"


@pytest.mark.asyncio
async def test_agent_with_tools_full_loop() -> None:
    """Test agent with tools completes full ReAct loop."""
    # Model that first calls tool, then responds
    call_count = 0

    def response_fn(messages, tools):
        nonlocal call_count
        call_count += 1

        # First call: return tool call
        if call_count == 1:
            return {
                "content": "Let me echo that.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "echo",
                        "arguments": {"message": "Echoed message"},
                    }
                ],
            }
        # Second call: return final response
        return "I've completed the task."

    model = FakeModel(name="test", response_fn=response_fn)
    agent = TestAgent(name="test_agent", model=model, tools=[EchoTool()])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Echo this message")

        # Verify full loop completed
        assert result.output is not None
        assert (
            "completed" in result.output.content.lower()
            or "echoed" in result.output.content.lower()
        )

        # Verify tool was called
        tool_messages = [m for m in result.messages if m.role.value == "tool"]
        assert len(tool_messages) > 0

        # Verify model was called multiple times (tool call + final response)
        assert call_count >= 2
