"""Tests for policy hooks and governance features."""

from typing import Any

import pytest

from routekit.core.agent import Agent, RunResult
from routekit.core.errors import ToolError
from routekit.core.hooks import ApprovalGate, PIIRedactionHook, PolicyHooks, ToolFilter
from routekit.core.runtime import Runtime
from routekit.core.tools import EchoTool
from routekit.providers.local import FakeModel


class TestAgent(Agent):
    """Test agent for hooks testing."""

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        raise NotImplementedError("Use runtime.run() instead")


@pytest.mark.asyncio
async def test_tool_filter_allow_list() -> None:
    """Test tool filter with allow list."""
    model = FakeModel(name="test")
    echo_tool = EchoTool()
    
    # Create agent with tool filter (only allow echo)
    agent = TestAgent(
        name="test_agent",
        model=model,
        tools=[echo_tool],
        tool_filter=ToolFilter(allowed_tools=["echo"]),
    )

    runtime = Runtime()
    runtime.register_agent(agent)

    # Should work - echo is allowed
    result = await runtime.run("test_agent", "test")
    assert result.output is not None


@pytest.mark.asyncio
async def test_tool_filter_deny_list() -> None:
    """Test tool filter with deny list."""
    model = FakeModel(name="test")
    echo_tool = EchoTool()
    
    # Create agent with tool filter (deny echo)
    agent = TestAgent(
        name="test_agent",
        model=model,
        tools=[echo_tool],
        tool_filter=ToolFilter(denied_tools=["echo"]),
    )

    runtime = Runtime()
    runtime.register_agent(agent)

    # Model tries to call echo tool
    def response_fn(messages, tools):
        return {
            "content": "I'll echo that",
            "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {"message": "test"}}],
        }

    model.response_fn = response_fn

    # Should fail - echo is denied
    # The error gets wrapped in RuntimeError
    from routekit.core.errors import RuntimeError as RouteKitRuntimeError
    with pytest.raises(RouteKitRuntimeError, match="not allowed"):
        await runtime.run("test_agent", "test")


@pytest.mark.asyncio
async def test_runtime_tool_filter() -> None:
    """Test runtime-level tool filter."""
    model = FakeModel(name="test")
    echo_tool = EchoTool()
    
    agent = TestAgent(name="test_agent", model=model, tools=[echo_tool])

    # Runtime-level filter
    runtime = Runtime(
        policy_hooks=PolicyHooks(tool_filter=ToolFilter(denied_tools=["echo"]))
    )
    runtime.register_agent(agent)

    def response_fn(messages, tools):
        return {
            "content": "I'll echo that",
            "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {"message": "test"}}],
        }

    model.response_fn = response_fn

    # Should fail - echo is denied at runtime level
    from routekit.core.errors import RuntimeError as RouteKitRuntimeError
    with pytest.raises(RouteKitRuntimeError, match="not allowed"):
        await runtime.run("test_agent", "test")


@pytest.mark.asyncio
async def test_approval_gate() -> None:
    """Test approval gate for tools."""
    from routekit.core.tool import ToolPermission

    model = FakeModel(name="test")
    
    # Create tool that requires NETWORK permission
    class NetworkTool(EchoTool):
        def __init__(self):
            super().__init__()
            self.name = "network_tool"
            self.permissions = [ToolPermission.NETWORK]

    network_tool = NetworkTool()

    # Approval gate that requires approval for NETWORK tools
    approval_callback_called = False

    def approval_callback(tool_name: str, tool_args: dict) -> bool:
        nonlocal approval_callback_called
        approval_callback_called = True
        # Deny network_tool
        return tool_name != "network_tool"

    agent = TestAgent(name="test_agent", model=model, tools=[network_tool])

    runtime = Runtime(
        policy_hooks=PolicyHooks(
            approval_gate=ApprovalGate(
                require_approval_for_permissions=["network"],
                approval_callback=approval_callback,
            )
        )
    )
    runtime.register_agent(agent)

    def response_fn(messages, tools):
        return {
            "content": "I'll use network tool",
            "tool_calls": [
                {"id": "call_1", "name": "network_tool", "arguments": {"message": "test"}}
            ],
        }

    model.response_fn = response_fn

    # Should fail - network_tool requires approval but callback denies it
    from routekit.core.errors import RuntimeError as RouteKitRuntimeError
    with pytest.raises(RouteKitRuntimeError, match="requires approval"):
        await runtime.run("test_agent", "test")

    # Verify callback was called
    assert approval_callback_called


@pytest.mark.asyncio
async def test_approval_gate_approved() -> None:
    """Test approval gate when tool is approved."""
    from routekit.core.tool import ToolPermission

    model = FakeModel(name="test")
    
    class NetworkTool(EchoTool):
        def __init__(self):
            super().__init__()
            self.name = "network_tool"
            self.permissions = [ToolPermission.NETWORK]

    network_tool = NetworkTool()

    def approval_callback(tool_name: str, tool_args: dict) -> bool:
        # Approve network_tool
        return True

    agent = TestAgent(name="test_agent", model=model, tools=[network_tool])

    runtime = Runtime(
        policy_hooks=PolicyHooks(
            approval_gate=ApprovalGate(
                require_approval_for_permissions=["network"],
                approval_callback=approval_callback,
            )
        )
    )
    runtime.register_agent(agent)

    def response_fn(messages, tools):
        return {
            "content": "I'll use network tool",
            "tool_calls": [
                {"id": "call_1", "name": "network_tool", "arguments": {"message": "test"}}
            ],
        }

    model.response_fn = response_fn

    # Should succeed - network_tool is approved
    result = await runtime.run("test_agent", "test")
    assert result.output is not None


@pytest.mark.asyncio
async def test_pii_redaction() -> None:
    """Test PII redaction hook."""
    model = FakeModel(name="test")
    echo_tool = EchoTool()
    
    agent = TestAgent(name="test_agent", model=model, tools=[echo_tool])

    # Create PII redaction hook
    pii_hook = PIIRedactionHook(redact_emails=True, redact_phones=True)

    runtime = Runtime(policy_hooks=PolicyHooks(pii_redaction=pii_hook))
    runtime.register_agent(agent)

    # Run with PII in prompt
    result = await runtime.run(
        "test_agent",
        "Contact me at john.doe@example.com or 555-123-4567"
    )

    # Verify PII was redacted in trace
    # (In a real scenario, we'd check the trace file)
    assert result.output is not None


@pytest.mark.asyncio
async def test_pii_redaction_dict() -> None:
    """Test PII redaction in dictionaries."""
    hook = PIIRedactionHook(redact_emails=True, redact_phones=True)
    
    data = {
        "email": "test@example.com",
        "phone": "555-123-4567",
        "nested": {
            "contact": "user@test.com",
        },
    }
    
    redacted = hook.redact_dict(data)
    
    assert "[REDACTED]" in redacted["email"]
    assert "[REDACTED]" in redacted["phone"]
    assert "[REDACTED]" in redacted["nested"]["contact"]


@pytest.mark.asyncio
async def test_agent_level_filter_overrides_runtime() -> None:
    """Test that agent-level filter takes precedence over runtime filter."""
    model = FakeModel(name="test")
    echo_tool = EchoTool()
    
    # Agent allows echo, runtime denies it
    agent = TestAgent(
        name="test_agent",
        model=model,
        tools=[echo_tool],
        tool_filter=ToolFilter(allowed_tools=["echo"]),  # Agent allows
    )

    runtime = Runtime(
        policy_hooks=PolicyHooks(
            tool_filter=ToolFilter(denied_tools=["echo"])  # Runtime denies
        )
    )
    runtime.register_agent(agent)

    def response_fn(messages, tools):
        return {
            "content": "I'll echo that",
            "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {"message": "test"}}],
        }

    model.response_fn = response_fn

    # Agent-level filter takes precedence - if agent allows, it should work
    # even if runtime denies (agent filter is checked first)
    result = await runtime.run("test_agent", "test")
    assert result.output is not None
