"""Tests for Tool primitive."""

import pytest
from pydantic import BaseModel, Field

from routekit.core.errors import ToolError
from routekit.core.tool import Tool, ToolPermission


class AddInput(BaseModel):
    """Input model for add tool."""

    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")


class AddOutput(BaseModel):
    """Output model for add tool."""

    result: int = Field(..., description="Sum of a and b")


class AddTool(Tool):
    """Simple addition tool."""

    def __init__(self) -> None:
        super().__init__(
            name="add",
            description="Add two numbers",
            input_model=AddInput,
            output_model=AddOutput,
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute addition."""
        if not isinstance(input, AddInput):
            raise ToolError("Invalid input type")
        return AddOutput(result=input.a + input.b)


class SimpleInput(BaseModel):
    """Simple input model."""

    value: str = Field(..., description="Input value")


class SimpleOutput(BaseModel):
    """Simple output model."""

    result: str = Field(..., description="Output value")


class SimpleTool(Tool):
    """Simple tool without permissions."""

    def __init__(self) -> None:
        super().__init__(
            name="simple",
            description="Simple tool",
            input_model=SimpleInput,
            output_model=SimpleOutput,
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute simple transformation."""
        if not isinstance(input, SimpleInput):
            raise ToolError("Invalid input type")
        return SimpleOutput(result=f"Processed: {input.value}")


def test_tool_creation() -> None:
    """Test tool creation."""
    tool = AddTool()
    assert tool.name == "add"
    assert tool.description == "Add two numbers"
    assert tool.input_model == AddInput
    assert tool.output_model == AddOutput


def test_tool_parameters_schema() -> None:
    """Test tool JSON schema generation."""
    tool = AddTool()
    schema = tool.parameters
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "a" in schema["properties"]
    assert "b" in schema["properties"]
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "integer"


def test_tool_execute() -> None:
    """Test tool execution with validation."""
    import asyncio

    tool = AddTool()
    result = asyncio.run(tool.execute(a=2, b=3))
    assert isinstance(result, AddOutput)
    assert result.result == 5


def test_tool_execute_invalid_input() -> None:
    """Test tool execution with invalid input."""
    import asyncio

    tool = AddTool()
    with pytest.raises(ToolError):
        asyncio.run(tool.execute(a="not a number", b=3))


def test_tool_with_permissions() -> None:
    """Test tool with permissions."""
    tool = AddTool()
    tool.permissions = [ToolPermission.NETWORK]
    assert ToolPermission.NETWORK in tool.permissions


def test_tool_with_rate_limit() -> None:
    """Test tool with rate limit."""
    tool = AddTool()
    tool.rate_limit = 10
    assert tool.rate_limit == 10


def test_tool_with_timeout() -> None:
    """Test tool with timeout."""
    tool = AddTool()
    tool.timeout = 5.0
    assert tool.timeout == 5.0


def test_tool_no_input_model() -> None:
    """Test tool without input model."""
    tool = SimpleTool()
    # Should still generate a schema (empty)
    schema = tool.parameters
    assert schema["type"] == "object"


def test_tool_execute_simple() -> None:
    """Test simple tool execution."""
    import asyncio

    tool = SimpleTool()
    result = asyncio.run(tool.execute(value="test"))
    assert isinstance(result, SimpleOutput)
    assert result.result == "Processed: test"


def test_tool_error_handling() -> None:
    """Test tool error handling."""
    import asyncio

    class FailingTool(Tool):
        def __init__(self) -> None:
            super().__init__(
                name="failing",
                description="A tool that fails",
                input_model=SimpleInput,
            )

        async def run(self, input: BaseModel) -> BaseModel:
            raise ValueError("Tool execution failed")

    tool = FailingTool()
    with pytest.raises(ToolError, match="execution failed"):
        asyncio.run(tool.execute(value="test"))
