"""Hello RouteKit - Simple end-to-end example."""

import asyncio
from pathlib import Path
from typing import Any

from routekitai.core.agent import Agent, RunResult
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.providers.local import FakeModel


class HelloAgent(Agent):
    """Concrete agent for the hello example."""

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        """Not used - runtime handles execution."""
        raise NotImplementedError("Use runtime.run() instead")


async def main() -> None:
    """Run a simple RouteKit agent."""
    # Create a fake model for testing
    model = FakeModel(
        name="fake",
        responses={
            "hello": "Hello! I'll echo your message.",
            "echo": {
                "content": "I'll use the echo tool to repeat your message.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "echo",
                        "arguments": {"message": "Hello from RouteKit!"},
                    }
                ],
            },
        },
    )

    # Create agent with model and tools
    agent = HelloAgent(
        name="hello_agent",
        model=model,
        tools=[EchoTool()],
    )

    # Create runtime with tracing
    trace_dir = Path(".routekit") / "traces"
    runtime = Runtime(trace_dir=trace_dir)
    runtime.register_agent(agent)

    # Run the agent
    print("Running RouteKit agent...")
    result = await runtime.run("hello_agent", "Hello! Please echo 'Hello from RouteKit!'")

    # Print results
    print(f"\nOutput: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")
    print(f"Messages: {len(result.messages)}")

    # Verify trace file exists
    trace_file = trace_dir / f"{result.trace_id}.jsonl"
    if trace_file.exists():
        print(f"\nTrace file created: {trace_file}")
    else:
        print(f"\nWarning: Trace file not found at {trace_file}")


if __name__ == "__main__":
    asyncio.run(main())
