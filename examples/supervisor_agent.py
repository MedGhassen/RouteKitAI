"""Example: Supervisor policy with multi-agent delegation."""

import asyncio
from pathlib import Path

from routekit.core.agent import Agent
from routekit.core.policies import SupervisorPolicy
from routekit.core.policy_adapter import PolicyAdapter
from routekit.core.runtime import Runtime
from routekit.core.tools import EchoTool
from routekit.providers.local import FakeModel

# Note: Agent is now a concrete class, no need to subclass


async def main() -> None:
    """Run supervisor policy example."""
    print("Running supervisor policy example...")

    # Create models
    supervisor_model = FakeModel(name="supervisor")
    supervisor_model.add_response("I'll delegate this to the research agent.")

    research_model = FakeModel(name="research")
    research_model.add_response(
        "Research completed: RouteKit is a graph-native agent orchestration framework."
    )

    analysis_model = FakeModel(name="analysis")
    analysis_model.add_response("Analysis: The framework supports tracing and replay.")

    # Create agents
    supervisor = Agent(name="supervisor", model=supervisor_model, tools=[])
    research_agent = Agent(name="research_agent", model=research_model, tools=[EchoTool()])
    analysis_agent = Agent(name="analysis_agent", model=analysis_model, tools=[])

    # Create runtime
    trace_dir = Path(".routekit") / "traces"
    runtime = Runtime(trace_dir=trace_dir)
    runtime.register_agent(supervisor)
    runtime.register_agent(research_agent)
    runtime.register_agent(analysis_agent)

    # Create supervisor policy
    supervisor_policy = SupervisorPolicy(
        sub_agents={
            "research_agent": research_agent,
            "analysis_agent": analysis_agent,
        },
        runtime=runtime,
        delegation_keywords={
            "research_agent": ["research", "information", "gather"],
            "analysis_agent": ["analyze", "process", "data"],
        },
    )

    policy = PolicyAdapter(supervisor_policy)

    # Run supervisor
    result = await runtime.run("supervisor", "Research information about RouteKit", policy=policy)

    print("\nSupervisor result:")
    print(f"  Output: {result.output.content}")
    print(f"  Trace ID: {result.trace_id}")
    print(f"  Messages: {len(result.messages)}")


if __name__ == "__main__":
    asyncio.run(main())
