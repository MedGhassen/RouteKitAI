"""Tests for Tool system enhancements."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from pydantic import BaseModel, Field

from routekit.core.errors import ToolError
from routekit.core.tool import Tool, ToolPermission
from routekit.core.tools import EchoTool, FileReadTool, HttpGetTool
from routekit.observability.trace import Trace


class TestInput(BaseModel):
    """Test input with sensitive field."""

    message: str = Field(..., description="Message")
    api_key: str = Field(..., description="API key")
    password: str = Field(..., description="Password")


class TestOutput(BaseModel):
    """Test output."""

    result: str = Field(..., description="Result")


class TestToolWithRedaction(Tool):
    """Test tool with redaction."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="test_redaction",
            description="Test tool with redaction",
            input_model=TestInput,
            output_model=TestOutput,
            redact_fields=["api_key", "password"],
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute test tool."""
        if not isinstance(input, TestInput):
            raise ToolError("Invalid input")
        return TestOutput(result=f"Processed: {input.message}")


class SlowTool(Tool):
    """Tool that sleeps for testing timeout."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, sleep_time: float = 1.0) -> None:
        super().__init__(
            name="slow_tool",
            description="Slow tool for testing",
            timeout=0.1,  # 100ms timeout
        )
        object.__setattr__(self, "sleep_time", sleep_time)

    async def run(self, input: BaseModel) -> BaseModel:
        """Sleep then return."""
        await asyncio.sleep(self.sleep_time)
        return TestOutput(result="done")


class FailingTool(Tool):
    """Tool that fails for testing retries."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, fail_count: int = 2) -> None:
        super().__init__(
            name="failing_tool",
            description="Tool that fails then succeeds",
            input_model=TestInput,
            output_model=TestOutput,
        )
        object.__setattr__(self, "fail_count", fail_count)
        object.__setattr__(self, "call_count", 0)

    async def run(self, input: BaseModel) -> BaseModel:
        """Fail a few times then succeed."""
        current_count = getattr(self, "call_count", 0)
        object.__setattr__(self, "call_count", current_count + 1)
        if current_count < self.fail_count:
            raise ValueError("Intentional failure")
        return TestOutput(result="success")


def test_tool_schema_generation() -> None:
    """Test that tool schema matches pydantic model."""
    tool = EchoTool()
    schema = tool.parameters

    # Check schema structure
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "message" in schema["properties"]
    assert schema["properties"]["message"]["type"] == "string"

    # Verify schema matches input model
    from routekit.core.tools import EchoInput

    expected_schema = EchoInput.model_json_schema()
    assert schema == expected_schema


def test_tool_redaction() -> None:
    """Test that tool redaction works."""
    tool = TestToolWithRedaction()

    # Test redaction
    data = {
        "message": "Hello",
        "api_key": "secret-key-123",
        "password": "secret-password",
        "other_field": "not-redacted",
    }

    redacted = tool.redact_data(data)
    assert redacted["message"] == "Hello"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["other_field"] == "not-redacted"


def test_tool_redaction_in_trace() -> None:
    """Test that redaction works in trace events."""
    tool = TestToolWithRedaction()
    trace = Trace(trace_id="test-trace")

    # Add tool call event with redaction
    tool_args = {
        "message": "Hello",
        "api_key": "secret-key-123",
        "password": "secret-password",
    }

    redacted_args = tool.redact_data(tool_args)
    trace.add_event("tool_called", {"tool": tool.name, "arguments": redacted_args})

    # Verify redaction in trace
    events = trace.get_events_by_type("tool_called")
    assert len(events) == 1
    event_data = events[0].data
    assert event_data["arguments"]["api_key"] == "[REDACTED]"
    assert event_data["arguments"]["password"] == "[REDACTED]"
    assert event_data["arguments"]["message"] == "Hello"


@pytest.mark.asyncio
async def test_echo_tool() -> None:
    """Test EchoTool."""
    tool = EchoTool()
    result = await tool.execute(message="Hello, world!")

    assert result.echoed == "Hello, world!"


@pytest.mark.asyncio
async def test_file_read_tool() -> None:
    """Test FileReadTool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_content = "Hello, file!"
        test_file.write_text(test_content)

        tool = FileReadTool()
        result = await tool.execute(path=str(test_file))

        assert result.content == test_content
        assert result.size == len(test_content.encode())


@pytest.mark.asyncio
async def test_file_read_tool_not_found() -> None:
    """Test FileReadTool with non-existent file."""
    tool = FileReadTool()
    with pytest.raises(ToolError, match="File not found"):
        await tool.execute(path="/nonexistent/file.txt")


@pytest.mark.asyncio
async def test_http_get_tool() -> None:
    """Test HttpGetTool (if httpx is available)."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    tool = HttpGetTool()
    # Test with a simple public API
    result = await tool.execute(url="https://httpbin.org/get", timeout=10.0)

    assert result.status_code == 200
    assert "url" in result.body.lower()  # httpbin returns request info


@pytest.mark.asyncio
async def test_http_get_tool_redaction() -> None:
    """Test that HttpGetTool redacts sensitive headers."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    tool = HttpGetTool()
    trace = Trace(trace_id="test-trace")

    # Test redaction of headers (nested in tool_args)
    tool_args = {
        "url": "https://httpbin.org/get",
        "headers": {
            "api_key": "secret-key-123",
            "authorization": "Bearer token-123",
            "content-type": "application/json",
        },
    }

    # Redact the entire tool_args dict (which includes nested headers)
    redacted_args = tool.redact_data(tool_args)
    trace.add_event("tool_called", {"tool": tool.name, "arguments": redacted_args})

    # Verify redaction in nested headers
    events = trace.get_events_by_type("tool_called")
    assert len(events) == 1
    event_data = events[0].data
    headers = event_data["arguments"]["headers"]
    assert headers["api_key"] == "[REDACTED]"
    assert headers["authorization"] == "[REDACTED]"
    assert headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_tool_timeout() -> None:
    """Test tool timeout behavior."""
    from routekit.core.runtime import Runtime

    tool = SlowTool(sleep_time=1.0)  # Sleep for 1 second
    # Tool has 0.1s timeout
    runtime = Runtime(max_retries=0, timeout=0.1)

    with pytest.raises(ToolError, match="timed out"):
        await runtime._execute_tool(tool, {}, Trace(trace_id="test"), None)


@pytest.mark.asyncio
async def test_tool_retry() -> None:
    """Test tool retry behavior."""
    from routekit.core.runtime import Runtime

    # Create tool that fails twice then succeeds
    tool = FailingTool(fail_count=2)
    runtime = Runtime(max_retries=3)  # Allow 3 retries

    # Tool should succeed after retries
    # FailingTool needs TestInput with all required fields
    result = await runtime._execute_tool(
        tool,
        {"message": "test", "api_key": "dummy", "password": "dummy"},
        Trace(trace_id="test"),
        None
    )
    assert result is not None


@pytest.mark.asyncio
async def test_tool_retry_exhausted() -> None:
    """Test tool retry exhaustion."""
    from routekit.core.runtime import Runtime

    # Create tool that always fails
    tool = FailingTool(fail_count=10)  # Will fail more than retries
    runtime = Runtime(max_retries=2)  # Only 2 retries

    with pytest.raises(ToolError):
        await runtime._execute_tool(tool, {}, Trace(trace_id="test"), None)
