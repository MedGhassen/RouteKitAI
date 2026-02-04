"""Basic example of using RouteKit."""

import asyncio

from routekitai import Agent
from routekitai.core.tools import EchoTool
from routekitai.providers.local import FakeModel


async def main() -> None:
    """Run a basic routekitai example (no API key required)."""
    # Use a fake model for local testing
    model = FakeModel(name="basic")
    model.add_response("Hello! I used the echo tool.")

    # Create an agent with the echo tool
    agent = Agent(
        name="assistant",
        model=model,
        tools=[EchoTool()],
    )

    # Run the agent
    result = await agent.run("Say hello and echo 'RouteKit works!'")
    print(f"Output: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
