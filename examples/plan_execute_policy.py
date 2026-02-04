"""Example: Plan-Execute Policy."""

import asyncio
from pathlib import Path

from routekitai.core.agent import Agent
from routekitai.core.model import Model, ModelResponse, Usage
from routekitai.core.policies import PlanExecutePolicy
from routekitai.core.policy_adapter import PolicyAdapter
from routekitai.core.runtime import Runtime


class MockModel(Model):
    """Mock model for example."""

    def __init__(self) -> None:
        super().__init__()
        object.__setattr__(self, "_name", "mock")
        object.__setattr__(self, "_provider", "test")
        object.__setattr__(self, "call_count", 0)

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        """Mock chat that returns plans."""
        object.__setattr__(self, "call_count", self.call_count + 1)
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

    plan_policy = PlanExecutePolicy()
    policy = PolicyAdapter(plan_policy)
    prompt = "Write a blog post about AI"
    result = await runtime.run("plan_agent", prompt, policy=policy)

    # Show steps: plan and execution outcomes from final_state and messages
    state = result.final_state
    plan = state.get("plan", [])
    if plan:
        print("Plan:")
        for i, step in enumerate(plan, start=1):
            # Step may already be "1. ..." from model; show as single numbered line
            step_text = step.strip()
            if step_text and step_text[0].isdigit():
                idx = 1
                while idx < len(step_text) and (step_text[idx].isdigit() or step_text[idx] in ".)"):
                    idx += 1
                step_text = step_text[idx:].strip() or step.strip()
            print(f"  {i}. {step_text}")
        print()
    # Execution outcomes = model's response each time we asked "Execute step: X"
    # Assistant messages: [0]=plan, [1]=outcome for step 1, [2]=outcome for step 2, ...
    assistant_msgs = [
        m for m in result.messages if getattr(m.role, "value", str(m.role)) == "assistant"
    ]
    if len(assistant_msgs) > 1:
        print("Execution outcomes (model output for each step):")
        for i, msg in enumerate(assistant_msgs[1:], start=1):
            step_label = plan[i - 1].strip() if i <= len(plan) else f"Step {i}"
            if step_label and step_label[0].isdigit():
                idx = 1
                while idx < len(step_label) and (
                    step_label[idx].isdigit() or step_label[idx] in ".)"
                ):
                    idx += 1
                step_label = step_label[idx:].strip() or step_label
            outcome = msg.content[:80] + ("..." if len(msg.content) > 80 else "")
            print(f"  {i}. {step_label}")
            print(f"     → {outcome}")
        print()
    print(f"Result: {result.output.content}")
    print(f"Trace ID: {result.trace_id}")


if __name__ == "__main__":
    asyncio.run(main())
