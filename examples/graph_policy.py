"""Example: Graph Policy."""

import asyncio
from pathlib import Path

from routekit.core.agent import Agent
from routekit.core.message import Message
from routekit.core.model import Model, ModelResponse, Usage
from routekit.core.policies import GraphPolicy
from routekit.core.policy_adapter import PolicyAdapter
from routekit.core.runtime import Runtime
from pydantic import BaseModel


class MockModel(Model):
    """Mock model for example."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "mock"
        self.provider = "test"

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat."""
        return ModelResponse(
            content="Graph execution would happen here. For now, this is a placeholder.",
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


async def main() -> None:
    """Run graph policy example."""
    model = MockModel()
    agent = Agent(name="graph_agent", model=model, tools=[])

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(agent)

    graph_policy = GraphPolicy()
    policy = PolicyAdapter(graph_policy)
    result = await runtime.run("graph_agent", "Execute a graph workflow", policy=policy)

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")
    print("\nNote: GraphPolicy is a placeholder. Full graph execution will be implemented in the graphs module.")


if __name__ == "__main__":
    asyncio.run(main())
