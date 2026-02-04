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
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_provider", "test")

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

    runtime = Runtime(trace_dir=Path(".routekit/traces"))
    runtime.register_agent(supervisor)
    runtime.register_agent(research_agent)

    # Policy needs runtime to execute delegated sub-agent
    supervisor_policy = SupervisorPolicy(
        sub_agents={"research_agent": research_agent},
        runtime=runtime,
        delegation_keywords={"research_agent": ["research", "impact", "ai"]},
    )
    policy = PolicyAdapter(supervisor_policy)

    prompt = "Research the impact of AI"
    result = await runtime.run("supervisor", prompt, policy=policy)

    # Show flow: input, supervisor decision, delegation, sub-agent output
    print("Flow:")
    print(f"  Input: {prompt!r}")
    state = result.final_state
    if state.get("delegated_agent"):
        print(f"  Delegated to: {state['delegated_agent']}")
    for i, msg in enumerate(result.messages):
        role = getattr(msg.role, "value", str(msg.role))
        short = msg.content[:70] + ("..." if len(msg.content) > 70 else "")
        label = " (supervisor)" if role == "assistant" and "delegate" in msg.content.lower() else ""
        label = (
            " (sub-agent result)"
            if role == "assistant" and "sub-agent" in msg.content.lower()
            else label
        )
        print(f"  {i + 1}. [{role}]{label} {short}")
    print()
    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
