"""Example: Function Calling Policy."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from routekitai.core.agent import Agent
from routekitai.core.model import Model, ModelResponse, ToolCall, Usage
from routekitai.core.policies import FunctionCallingPolicy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime
from routekitai.core.tool import Tool


class MockModel(Model):
    """Mock model for example."""

    def __init__(self) -> None:
        super().__init__()
        object.__setattr__(self, "_name", "mock")
        object.__setattr__(self, "_provider", "test")

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat with function calling."""
        return ModelResponse(
            content="I'll get the weather for you.",
            tool_calls=[
                ToolCall(id="call_1", name="get_weather", arguments={"city": "San Francisco"})
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


class WeatherInput(BaseModel):
    """Weather input."""

    city: str = Field(..., description="City name")


class WeatherOutput(BaseModel):
    """Weather output."""

    temperature: int = Field(..., description="Temperature in Fahrenheit")
    condition: str = Field(..., description="Weather condition")


class WeatherTool(Tool):
    """Weather tool."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="get_weather",
            description="Get weather for a city",
            input_model=WeatherInput,
            output_model=WeatherOutput,
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Get weather."""
        # Mock weather data
        return WeatherOutput(temperature=72, condition="Sunny")


async def main() -> None:
    """Run function calling policy example."""
    model = MockModel()
    tools = [WeatherTool()]
    agent = Agent(name="function_agent", model=model, tools=tools)

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(agent)

    func_policy = FunctionCallingPolicy()
    policy = PolicyAdapter(func_policy)
    result = await runtime.run(
        "function_agent", "What's the weather in San Francisco?", policy=policy
    )

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
