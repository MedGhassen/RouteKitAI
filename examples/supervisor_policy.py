"""Example: Supervisor Policy."""

import asyncio
from pathlib import Path

from routekitai.core.agent import Agent
from routekitai.core.model import Model, ModelResponse, Usage
from routekitai.core.policies import SupervisorPolicy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime


class MockModel(Model):
    """Mock model for example."""

    def __init__(self, name: str = "mock") -> None:
        super().__init__()
        self.name = name
        self.provider = "test"

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat."""
        content = "I'll delegate this to the research agent."
        if "research" in messages[-1].content.lower():
            content = "Research completed: AI is transforming many industries."
        return ModelResponse(
            content=content,
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


async def main() -> None:
    """Run supervisor policy example."""
    # Create supervisor agent
    supervisor_model = MockModel("supervisor")
    supervisor = Agent(name="supervisor", model=supervisor_model, tools=[])

    # Create sub-agents
    research_model = MockModel("research")
    research_agent = Agent(name="research_agent", model=research_model, tools=[])

    # Create policy with sub-agents
    supervisor_policy = SupervisorPolicy()
    supervisor_policy.sub_agents = {"research_agent": research_agent}
    policy = PolicyAdapter(supervisor_policy)

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(supervisor)

    result = await runtime.run("supervisor", "Research the impact of AI", policy=policy)

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
