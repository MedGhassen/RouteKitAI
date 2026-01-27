"""Example: ReAct Policy."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from routekitai.core.agent import Agent
from routekitai.core.model import Model, ModelResponse, ToolCall, Usage
from routekitai.core.policies import ReActPolicy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime
from routekitai.core.tool import Tool


class MockModel(Model):
    """Mock model for example."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "mock"
        self.provider = "test"
        self.call_count = 0

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat that returns tool calls."""
        self.call_count += 1
        if self.call_count == 1:
            # First call: return tool call
            return ModelResponse(
                content="I'll calculate that for you.",
                tool_calls=[
                    ToolCall(id="call_1", name="calculator", arguments={"a": 2, "b": 3, "op": "+"})
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )
        # Second call: return final answer
        return ModelResponse(
            content="The result is 5.",
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class CalculatorInput(BaseModel):
    """Calculator input."""

    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")
    op: str = Field(..., description="Operation: +, -, *, /")


class CalculatorOutput(BaseModel):
    """Calculator output."""

    result: int = Field(..., description="Calculation result")


class CalculatorTool(Tool):
    """Simple calculator tool."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="calculator",
            description="Perform arithmetic operations",
            input_model=CalculatorInput,
            output_model=CalculatorOutput,
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute calculation."""
        calc_input = input
        a = calc_input.a
        b = calc_input.b
        op = calc_input.op

        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        elif op == "*":
            result = a * b
        elif op == "/":
            result = a // b
        else:
            raise ValueError(f"Unknown operation: {op}")

        return CalculatorOutput(result=result)


async def main() -> None:
    """Run ReAct policy example."""
    # Create agent
    model = MockModel()
    tools = [CalculatorTool()]
    agent = Agent(name="react_agent", model=model, tools=tools)

    # Create runtime with ReAct policy
    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(agent)

    # Run with ReAct policy (using adapter)
    react_policy = ReActPolicy(max_iterations=10)
    policy = PolicyAdapter(react_policy)
    result = await runtime.run("react_agent", "What is 2 + 3?", policy=policy)

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
