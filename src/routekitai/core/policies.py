"""Concrete policy implementations for RouteKit."""

from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.agent import Agent
from routekitai.core.message import Message, MessageRole
from routekitai.core.model import ModelResponse
from routekitai.core.policy import (
    Action,
    Final,
    ModelAction,
    Parallel,
    Policy,
    ToolAction,
)
from routekitai.core.runtime import Runtime
from routekitai.graphs.graph import Graph


class ReActPolicy(Policy):
    """ReAct (Reasoning + Acting) policy.

    Simple loop: model -> decide tool -> tool -> model -> final
    """

    max_iterations: int = 10

    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan next action in ReAct loop.

        Args:
            state: Current state with agent, messages, etc.

        Returns:
            List of actions (single action per step)
        """
        messages: list[Message] = state.get("messages", [])
        iteration: int = state.get("iteration", 0)

        if iteration >= self.max_iterations:
            # Finalize with last message
            if messages and messages[-1].role == MessageRole.ASSISTANT:
                return [Final(output=messages[-1])]
            return [Final(output=Message.assistant("Max iterations reached"))]

        # If no messages or last message is not assistant, call model
        if not messages or messages[-1].role != MessageRole.ASSISTANT:
            return [ModelAction(messages=messages)]

        # Check for tool calls in last message
        last_message = messages[-1]
        if last_message.tool_calls:
            # Execute tool calls (can be parallel)
            tool_actions: list[Action] = [
                ToolAction(
                    tool_name=tc["name"],
                    tool_input=tc.get("arguments", {}),
                    tool_call_id=tc.get("id", ""),
                )
                for tc in last_message.tool_calls
            ]
            if len(tool_actions) > 1:
                return [Parallel(actions=tool_actions)]
            return tool_actions

        # If assistant message with no tool calls, we're done
        return [Final(output=last_message)]


class FunctionCallingPolicy(Policy):
    """Strict function calling policy.

    Only allows tool calls that match available tool schemas.
    No free-form tool names.
    """

    max_iterations: int = 10

    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan next action with strict function calling.

        Args:
            state: Current state

        Returns:
            List of actions
        """
        agent: Agent = state["agent"]
        messages: list[Message] = state.get("messages", [])
        iteration: int = state.get("iteration", 0)

        if iteration >= self.max_iterations:
            if messages and messages[-1].role == MessageRole.ASSISTANT:
                return [Final(output=messages[-1])]
            return [Final(output=Message.assistant("Max iterations reached"))]

        # If no messages, start with model call
        if not messages:
            return [
                ModelAction(messages=[], prompt="You are a helpful assistant with access to tools.")
            ]

        # If last message is not assistant, call model
        if messages[-1].role != MessageRole.ASSISTANT:
            return [ModelAction(messages=messages)]

        # Check for tool calls
        last_message = messages[-1]
        if last_message.tool_calls:
            # Validate tool calls against available tools
            tool_names = {t.name for t in agent.tools}
            valid_actions: list[Action] = []
            for tc in last_message.tool_calls:
                tool_name = tc["name"]
                if tool_name not in tool_names:
                    # Invalid tool name - skip
                    continue
                valid_actions.append(
                    ToolAction(
                        tool_name=tool_name,
                        tool_input=tc.get("arguments", {}),
                        tool_call_id=tc.get("id", ""),
                    )
                )

            if not valid_actions:
                # No valid tools, finalize
                return [Final(output=Message.assistant("No valid tools available"))]

            if len(valid_actions) > 1:
                return [Parallel(actions=valid_actions)]
            return valid_actions

        # Done
        return [Final(output=last_message)]


class GraphPolicy(Policy, BaseModel):
    """Graph-based policy that delegates to graphs module execution."""

    model_config = {"arbitrary_types_allowed": True}

    graph: Graph = Field(..., description="Graph to execute")
    runtime: Runtime | None = Field(default=None, description="Runtime for graph execution")

    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan using graph execution.

        Args:
            state: Current state

        Returns:
            List of actions
        """
        from routekitai.graphs.executors import GraphExecutor

        # Get runtime from state or use instance runtime
        runtime = state.get("runtime") or self.runtime
        if not runtime:
            raise ValueError("GraphPolicy requires a Runtime instance")

        # Create executor
        executor = GraphExecutor(runtime=runtime, graph=self.graph)

        # Extract input from state (prompt or messages)
        messages = state.get("messages", [])
        if messages:
            # Get prompt from last user message
            prompt = None
            for msg in reversed(messages):
                if hasattr(msg, "role") and msg.role.value == "user":
                    prompt = msg.content if hasattr(msg, "content") else str(msg)
                    break
            input_data = {"prompt": prompt or ""}
        else:
            input_data = state.get("input_data", {})

        # Execute graph
        graph_result = await executor.execute(input_data=input_data)

        # Store on runtime so callers can inspect steps and state (e.g. for logging)
        if runtime is not None:
            runtime._last_graph_result = graph_result

        # Return final output as result
        final_output = graph_result.get("state", {}).get("output") or graph_result.get(
            "state", {}
        ).get("final_output", "Graph execution completed")
        return [Final(output=Message.assistant(str(final_output)))]


class PlanExecutePolicy(Policy):
    """Plan-Execute policy: plan steps, then execute them."""

    max_plan_steps: int = 10
    max_iterations: int = 20

    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan execution steps.

        Args:
            state: Current state

        Returns:
            List of actions
        """
        messages: list[Message] = state.get("messages", [])
        phase: str = state.get("phase", "planning")
        iteration: int = state.get("iteration", 0)

        if iteration >= self.max_iterations:
            return [Final(output=Message.assistant("Max iterations reached"))]

        if phase == "planning":
            # Planning phase: ask model to create a plan
            planning_prompt = (
                "Create a step-by-step plan to solve this task. List the steps clearly."
            )
            if messages:
                planning_prompt = f"{messages[0].content}\n\n{planning_prompt}"

            return [ModelAction(messages=[Message.user(planning_prompt)])]

        elif phase == "executing":
            # Execution phase: execute planned steps
            plan: list[str] = state.get("plan", [])
            current_step: int = state.get("current_step", 0)

            if current_step >= len(plan):
                # All steps executed
                return [Final(output=Message.assistant("Plan execution completed"))]

            # Execute current step
            step = plan[current_step]
            return [ModelAction(messages=[Message.user(f"Execute step: {step}")])]

        # Default: start planning
        return [ModelAction(messages=messages)]

    async def reflect(self, state: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        """Reflect and update state based on observation.

        Args:
            state: Current state
            observation: Observation from last action

        Returns:
            Updated state
        """
        state = state.copy()
        state.setdefault("observations", []).append(observation)
        state["iteration"] = state.get("iteration", 0) + 1

        # Extract plan from model response if in planning phase
        if state.get("phase") == "planning" and "result" in observation:
            result = observation["result"]
            if isinstance(result, ModelResponse):
                # Simple plan extraction (split by lines)
                plan_lines = [
                    line.strip()
                    for line in result.content.split("\n")
                    if line.strip() and line.strip()[0].isdigit()
                ]
                if plan_lines:
                    state["plan"] = plan_lines
                    state["phase"] = "executing"
                    state["current_step"] = 0

        # Update current step in execution phase
        if state.get("phase") == "executing":
            state["current_step"] = state.get("current_step", 0) + 1

        return state


class SupervisorPolicy(Policy, BaseModel):
    """Supervisor policy for multi-agent coordination.

    Supervisor delegates tasks to sub-agents with constrained toolsets and merges results.
    """

    model_config = {"arbitrary_types_allowed": True}

    sub_agents: dict[str, Agent] = Field(
        default_factory=dict, description="Sub-agents available for delegation"
    )
    runtime: Any = Field(default=None, description="Runtime for executing sub-agents")
    max_iterations: int = Field(default=20, description="Maximum iterations")
    delegation_keywords: dict[str, list[str]] = Field(
        default_factory=dict, description="Keywords to identify which agent to delegate to"
    )

    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan using supervisor delegation.

        Args:
            state: Current state (should not be mutated directly)

        Returns:
            List of actions
        """
        messages: list[Message] = state.get("messages", [])
        iteration: int = state.get("iteration", 0)
        runtime: Runtime | None = state.get("runtime") or self.runtime

        if iteration >= self.max_iterations:
            return [Final(output=Message.assistant("Max iterations reached"))]

        # Sub-agent just completed: finalize with its result (runtime set waiting_for_subagent=False)
        subagent_result = state.get("subagent_result")
        if subagent_result and not state.get("waiting_for_subagent"):
            if isinstance(subagent_result, dict) and "output" in subagent_result:
                content = subagent_result["output"]
                if hasattr(content, "content"):
                    content = content.content
                else:
                    content = str(content)
            else:
                content = str(subagent_result)
            return [Final(output=Message.assistant(content))]

        # If no messages, supervisor decides which agent to use
        if not messages:
            # Supervisor prompt to choose agent
            agent_list = ", ".join(self.sub_agents.keys())
            prompt = (
                f"You are a supervisor coordinating multiple agents. "
                f"Available agents: {agent_list}. "
                f"Analyze the task and delegate to the appropriate agent. "
                f"Respond with the agent name you want to delegate to."
            )
            return [ModelAction(messages=[Message.user(prompt)])]

        # Check if supervisor has delegated
        last_message = messages[-1]
        if last_message.role == MessageRole.ASSISTANT and not state.get("delegated_agent"):
            # Supervisor responded - check if it's a delegation
            content = last_message.content.lower()
            delegated_agent = None

            # Check for explicit agent mentions
            for agent_name, keywords in self.delegation_keywords.items():
                if any(keyword.lower() in content for keyword in keywords):
                    delegated_agent = agent_name
                    break

            # Fallback: check if agent name appears in content
            if not delegated_agent:
                for agent_name in self.sub_agents.keys():
                    if agent_name.lower() in content:
                        delegated_agent = agent_name
                        break

            if delegated_agent and delegated_agent in self.sub_agents:
                # Delegate to sub-agent
                state["delegated_agent"] = delegated_agent
                state["waiting_for_subagent"] = True

                # Extract task from original prompt
                original_prompt = messages[0].content if messages else "Complete the task"

                # Return a special action that will trigger sub-agent execution
                # This is handled by the runtime adapter
                return [
                    ModelAction(
                        messages=[Message.user(f"DELEGATE:{delegated_agent}:{original_prompt}")]
                    )
                ]

        # Check if we need to execute sub-agent (handled by adapter)
        if state.get("delegated_agent") and state.get("waiting_for_subagent") and runtime:
            # This will be handled by the adapter
            pass

        # Default: continue with supervisor
        return [ModelAction(messages=messages)]
