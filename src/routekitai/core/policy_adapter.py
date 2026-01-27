"""Adapter to bridge new Policy system with Runtime's Policy interface."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from routekitai.core.message import Message
from routekitai.core.policy import Final, ModelAction, Parallel, Policy, ToolAction
from routekitai.core.runtime import Policy as RuntimePolicy
from routekitai.core.runtime import Step

if TYPE_CHECKING:
    from routekitai.core.agent import Agent


class PolicyAdapter(RuntimePolicy):
    """Adapter to use new Action-based Policy with Runtime's Step-based interface."""

    def __init__(self, policy: Policy) -> None:
        """Initialize adapter with Action-based policy.

        Args:
            policy: Action-based policy to adapt
        """
        self.policy = policy
        self.state: dict[str, Any] = {}

    async def next_steps(
        self,
        agent: Agent,
        messages: list[Message],
        state: dict[str, Any],
    ) -> list[Step]:
        """Convert Action-based policy to Step-based interface.

        Args:
            agent: Agent instance
            messages: Current messages
            state: Current state

        Returns:
            List of steps
        """
        # Update policy state
        self.state = {
            "agent": agent,
            "messages": messages,
            "tools": agent.tools,
            "memory": agent.memory,  # Include memory in state
            "runtime": state.get("runtime"),  # Pass runtime to policy for sub-agent execution
            **state,
        }

        # Get actions from policy
        actions = await self.policy.plan(self.state)

        # Convert actions to steps
        steps = []
        for action in actions:
            if isinstance(action, ModelAction):
                # Check for special "DELEGATE" message from SupervisorPolicy
                if action.messages and action.messages[0].content.startswith("DELEGATE:"):
                    parts = action.messages[0].content.split(":", 2)
                    if len(parts) == 3:
                        subagent_name = parts[1]
                        subagent_prompt = parts[2]
                        steps.append(
                            Step(
                                step_id=str(uuid.uuid4()),
                                step_type="subagent_call",
                                input_data={
                                    "agent_name": subagent_name,
                                    "prompt": subagent_prompt,
                                },
                            )
                        )
                    else:
                        # Fallback if format is unexpected
                        steps.append(
                            Step(
                                step_id=str(uuid.uuid4()),
                                step_type="model_call",
                                input_data={
                                    "messages": action.messages
                                    or [Message.user(action.prompt or "")]
                                },
                            )
                        )
                else:
                    # Use messages directly if available, otherwise create from prompt
                    step_messages = (
                        action.messages if action.messages else [Message.user(action.prompt or "")]
                    )
                    steps.append(
                        Step(
                            step_id=str(uuid.uuid4()),
                            step_type="model_call",
                            input_data={"messages": step_messages},
                        )
                    )
            elif isinstance(action, ToolAction):
                steps.append(
                    Step(
                        step_id=str(uuid.uuid4()),
                        step_type="tool_call",
                        input_data={
                            "tool_name": action.tool_name,
                            "tool_args": action.tool_input,
                        },
                    )
                )
            elif isinstance(action, Parallel):
                # Create parallel tool call steps
                for sub_action in action.actions:
                    # Only handle ToolAction in parallel (other actions not supported yet)
                    if isinstance(sub_action, ToolAction):
                        steps.append(
                            Step(
                                step_id=str(uuid.uuid4()),
                                step_type="tool_call",
                                input_data={
                                    "tool_name": sub_action.tool_name,
                                    "tool_args": sub_action.tool_input,
                                },
                            )
                        )
                    # Other action types in parallel not yet supported
            elif isinstance(action, Final):
                # Final action - return empty to signal completion
                return []

        return steps
