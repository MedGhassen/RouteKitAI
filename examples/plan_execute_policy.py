"""Example: Plan-Execute Policy."""

import asyncio
from pathlib import Path

from routekit.core.agent import Agent
from routekit.core.model import Model, ModelResponse, Usage
from routekit.core.policies import PlanExecutePolicy
from routekit.core.policy_adapter import PolicyAdapter
from routekit.core.runtime import Runtime


class MockModel(Model):
    """Mock model for example."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "mock"
        self.provider = "test"
        self.call_count = 0

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat that returns plans."""
        self.call_count += 1
        if self.call_count == 1:
            # Planning phase
            return ModelResponse(
                content="1. Research the topic\n2. Write an outline\n3. Write the content\n4. Review and edit",
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )
        # Execution phase
        return ModelResponse(
            content="Step executed successfully.",
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


async def main() -> None:
    """Run plan-execute policy example."""
    model = MockModel()
    agent = Agent(name="plan_agent", model=model, tools=[])

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(agent)

    plan_policy = PlanExecutePolicy(max_plan_steps=10, max_iterations=20)
    policy = PolicyAdapter(plan_policy)
    result = await runtime.run("plan_agent", "Write a blog post about AI", policy=policy)

    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
