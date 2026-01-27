"""Tests for Message primitive."""

import json

from routekitai.core.message import Message, MessageRole


def test_message_creation() -> None:
    """Test basic message creation."""
    msg = Message(role=MessageRole.USER, content="Hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello"
    assert msg.metadata == {}
    assert msg.tool_calls is None
    assert msg.tool_result is None


def test_message_with_metadata() -> None:
    """Test message with metadata."""
    msg = Message(
        role=MessageRole.ASSISTANT,
        content="Response",
        metadata={"timestamp": "2024-01-01"},
    )
    assert msg.metadata["timestamp"] == "2024-01-01"


def test_message_helpers() -> None:
    """Test message helper methods."""
    system_msg = Message.system("You are a helpful assistant.")
    assert system_msg.role == MessageRole.SYSTEM
    assert system_msg.content == "You are a helpful assistant."

    user_msg = Message.user("Hello", key="value")
    assert user_msg.role == MessageRole.USER
    assert user_msg.content == "Hello"
    assert user_msg.metadata["key"] == "value"

    assistant_msg = Message.assistant("Hi there", tool_calls=[{"id": "1", "name": "test"}])
    assert assistant_msg.role == MessageRole.ASSISTANT
    assert assistant_msg.tool_calls == [{"id": "1", "name": "test"}]

    tool_msg = Message.tool("Result", {"value": 42})
    assert tool_msg.role == MessageRole.TOOL
    assert tool_msg.tool_result == {"value": 42}


def test_message_serialization() -> None:
    """Test message serialization to/from dict."""
    msg = Message.user("Hello", key="value")
    msg_dict = msg.to_dict()
    assert isinstance(msg_dict, dict)
    assert msg_dict["role"] == "user"
    assert msg_dict["content"] == "Hello"
    assert msg_dict["metadata"]["key"] == "value"

    # Deserialize
    msg2 = Message.from_dict(msg_dict)
    assert msg2.role == MessageRole.USER
    assert msg2.content == "Hello"
    assert msg2.metadata["key"] == "value"


def test_message_json_serialization() -> None:
    """Test message serialization to/from JSON."""
    msg = Message.assistant("Response", tool_calls=[{"id": "1", "name": "test"}])
    json_str = msg.to_json()
    assert isinstance(json_str, str)

    # Parse JSON to verify it's valid
    data = json.loads(json_str)
    assert data["role"] == "assistant"
    assert data["content"] == "Response"

    # Deserialize
    msg2 = Message.from_json(json_str)
    assert msg2.role == MessageRole.ASSISTANT
    assert msg2.content == "Response"
    assert msg2.tool_calls == [{"id": "1", "name": "test"}]


def test_message_with_tool_calls() -> None:
    """Test message with tool calls."""
    tool_calls = [
        {"id": "call_1", "name": "calculator", "arguments": {"a": 2, "b": 3}},
    ]
    msg = Message.assistant("I'll calculate that", tool_calls=tool_calls)
    assert msg.tool_calls == tool_calls


def test_message_with_tool_result() -> None:
    """Test message with tool result."""
    tool_result = {"result": 5, "operation": "add"}
    msg = Message.tool("Calculation complete", tool_result)
    assert msg.tool_result == tool_result
