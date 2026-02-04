"""Runtime/Orchestrator for RouteKit."""

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from routekitai.core.errors import ModelError, ToolError
from routekitai.core.errors import RuntimeError as RouteKitRuntimeError
from routekitai.core.hooks import PolicyHooks
from routekitai.core.message import Message, MessageRole
from routekitai.core.model import ModelResponse, StreamEvent
from routekitai.core.tool import Tool
from routekitai.observability.exporters.jsonl import JSONLExporter
from routekitai.observability.trace import Trace, TraceEvent
from routekitai.sandbox.permissions import PermissionManager

if TYPE_CHECKING:
    from routekitai.core.agent import Agent, RunResult


class Step(BaseModel):
    """A single execution step."""

    step_id: str = Field(..., description="Step ID")
    step_type: str = Field(..., description="Step type (model_call, tool_call, etc.)")
    input_data: dict[str, Any] = Field(..., description="Step input")
    output_data: dict[str, Any] | None = Field(default=None, description="Step output")
    latency_ms: float | None = Field(default=None, description="Step latency in milliseconds")
    error: str | None = Field(default=None, description="Error if step failed")


class Policy(ABC):
    """Policy interface for agent execution.

    A policy determines the next step(s) to execute based on current state.
    """

    @abstractmethod
    async def next_steps(
        self,
        agent: "Agent",
        messages: list[Message],
        state: dict[str, Any],
    ) -> list[Step]:
        """Determine next steps to execute.

        Args:
            agent: Agent instance
            messages: Current conversation messages
            state: Current agent state

        Returns:
            List of steps to execute (can be parallel)
        """
        raise NotImplementedError("Subclasses must implement next_steps")


class ReplayMismatchError(RouteKitRuntimeError):
    """Error raised when replay encounters a mismatch."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize replay mismatch error.

        Args:
            message: Error message
            context: Optional context (step_id, trace_id, etc.)
        """
        super().__init__(message, context=context)


class Runtime(BaseModel):
    """Step-based runtime with tracing, permissions, and replay."""

    agents: dict[str, "Agent"] = Field(default_factory=dict, description="Registered agents")
    trace_dir: Path | None = Field(default=None, description="Directory for trace files")
    max_retries: int = Field(default=3, description="Maximum retries for operations")
    timeout: float | None = Field(default=None, description="Default timeout in seconds")
    max_concurrency: int = Field(default=5, description="Maximum concurrent tool executions")
    permission_manager: PermissionManager | None = Field(
        default=None, description="Permission manager for tool execution"
    )
    policy_hooks: PolicyHooks | None = Field(
        default=None, description="Policy hooks for governance"
    )
    retry_backoff_base: float = Field(default=1.0, description="Base delay for exponential backoff")
    retry_backoff_max: float = Field(
        default=60.0, description="Maximum delay for exponential backoff"
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Runtime configuration")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize runtime with replay state."""
        super().__init__(**kwargs)
        self._replay_mode: bool = False
        self._replay_trace: Trace | None = None
        self._replay_step_index: int = 0
        self._replay_step_map: dict[str, TraceEvent] = {}  # Map step_id -> event for replay
        self._cancellation_token: asyncio.CancelledError | None = None
        # Progress tracking
        self._current_step: int = 0
        self._total_steps: int = 0
        self._progress_callbacks: list[Callable[[dict[str, Any]], None]] = []
        # Last graph execution result (set by GraphPolicy for callers to inspect steps/state)
        self._last_graph_result: dict[str, Any] | None = None

    def register_agent(self, agent: "Agent") -> None:
        """Register an agent with the runtime.

        Args:
            agent: Agent to register
        """
        self.agents[agent.name] = agent

    def add_progress_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Add a callback for progress updates.

        Args:
            callback: Function that receives progress dict with keys:
                     - current_step: int
                     - total_steps: int
                     - progress_percent: float
                     - current_step_type: str | None
        """
        self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Remove a progress callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    def _emit_progress(self, trace: Trace, step_type: str | None = None) -> None:
        """Emit progress update to callbacks and trace.

        Args:
            trace: Trace to add progress event to
            step_type: Optional current step type
        """
        progress_data = {
            "current_step": self._current_step,
            "total_steps": self._total_steps,
            "progress_percent": (
                (self._current_step / self._total_steps * 100) if self._total_steps > 0 else 0.0
            ),
            "current_step_type": step_type,
        }

        # Notify callbacks
        for callback in self._progress_callbacks:
            try:
                callback(progress_data)
            except Exception:
                # Don't let callback errors break execution
                pass

        # Add to trace
        trace.add_event("progress_update", progress_data)

    async def run(
        self,
        agent_name: str,
        prompt: str,
        policy: Policy | None = None,
        cancellation_token: asyncio.CancelledError | None = None,
        **kwargs: Any,
    ) -> "RunResult":
        """Run an agent with step-based execution and tracing.

        Args:
            agent_name: Name of the agent to run
            prompt: User prompt
            policy: Optional policy (uses agent's default if not provided)
            cancellation_token: Optional cancellation token for async cancellation
            **kwargs: Additional runtime parameters

        Returns:
            RunResult with trace_id and full execution details

        Raises:
            RouteKitRuntimeError: If runtime operation fails
            asyncio.CancelledError: If execution is cancelled
        """
        if agent_name not in self.agents:
            raise RouteKitRuntimeError(f"Agent {agent_name} not found")

        self._cancellation_token = cancellation_token

        agent = self.agents[agent_name]
        # In replay mode, reuse the original trace_id if available
        if self._replay_mode and self._replay_trace:
            trace_id = self._replay_trace.trace_id
        else:
            trace_id = str(uuid.uuid4())

        # Apply PII redaction to prompt if hook is configured
        redacted_prompt = prompt
        if self.policy_hooks and self.policy_hooks.pii_redaction:
            redacted_prompt = self.policy_hooks.pii_redaction.redact(prompt)

        trace = Trace(trace_id=trace_id, metadata={"agent": agent_name, "prompt": redacted_prompt})
        trace.add_event(
            "run_started", {"trace_id": trace_id, "agent": agent_name, "prompt": redacted_prompt}
        )

        # Export trace if trace_dir is set (lazy/async export)
        exporter = None
        export_task = None
        if self.trace_dir:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            exporter = JSONLExporter(output_dir=self.trace_dir)

        try:
            result = await self._execute_steps(agent, prompt, trace, policy, **kwargs)
            # Clean final_state to remove non-serializable objects before storing in trace
            cleaned_final_state: dict[str, Any] = {}
            for key, value in result.final_state.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    cleaned_final_state[key] = value
                elif isinstance(value, (list, dict)):
                    # Recursively clean nested structures
                    try:
                        json.dumps(value)  # Test if serializable
                        cleaned_final_state[key] = value
                    except (TypeError, ValueError):
                        # Convert to string if not serializable
                        cleaned_final_state[key] = str(value)
                else:
                    cleaned_final_state[key] = str(value)  # Convert to string representation

            # Store only serializable parts of result
            result_dict = {
                "output": result.output.model_dump(mode="json"),
                "trace_id": result.trace_id,
                "final_state": cleaned_final_state,
                "messages": [msg.model_dump(mode="json") for msg in result.messages],
            }
            trace.add_event("run_completed", {"trace_id": trace_id, "result": result_dict})

            # Export trace so it is on disk before returning (needed for replay and tests)
            if exporter and self.trace_dir:
                self.trace_dir.mkdir(parents=True, exist_ok=True)
                await exporter.export(trace)

            return result
        except asyncio.CancelledError:
            trace.add_event("cancelled", {"trace_id": trace_id})
            # Cancel export task if it exists
            if export_task and not export_task.done():
                export_task.cancel()
                try:
                    await export_task
                except asyncio.CancelledError:
                    pass
            if exporter:
                await exporter.export(trace)
            raise
        except (RouteKitRuntimeError, ToolError, ModelError) as e:
            # Re-raise known routkitai errors without wrapping
            trace.add_event(
                "error",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "context": getattr(e, "context", {}),
                },
            )
            if export_task and not export_task.done():
                export_task.cancel()
                try:
                    await export_task
                except asyncio.CancelledError:
                    pass
            if exporter:
                await exporter.export(trace)
            raise
        except Exception as e:
            trace.add_event(
                "error",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "context": {"trace_id": trace_id, "agent_name": agent_name},
                },
            )
            # Cancel export task if it exists
            if export_task and not export_task.done():
                export_task.cancel()
                try:
                    await export_task
                except asyncio.CancelledError:
                    pass
            if exporter:
                await exporter.export(trace)
            # Wrap unknown exceptions in RouteKitRuntimeError
            raise RouteKitRuntimeError(
                f"Runtime execution failed: {e}",
                context={
                    "trace_id": trace_id,
                    "agent_name": agent_name,
                    "error_type": type(e).__name__,
                },
            ) from e

    async def _execute_steps(
        self,
        agent: "Agent",
        prompt: str,
        trace: Trace,
        policy: Policy | None,
        **kwargs: Any,
    ) -> "RunResult":
        """Execute agent using step-based policy loop.

        Args:
            agent: Agent to execute
            prompt: User prompt
            trace: Trace for recording events
            policy: Policy for step execution
            **kwargs: Additional parameters

        Returns:
            RunResult
        """
        messages: list[Message] = [Message.user(prompt)]
        state: dict[str, Any] = {
            "memory": agent.memory,  # Make memory available to policies
            "runtime": self,  # Make runtime available for supervisor policy
        }

        # Use ReActPolicy as default if not provided
        if policy is None:
            from routekitai.core.policies import ReActPolicy
            from routekitai.core.policy_adapter import PolicyAdapter

            policy = PolicyAdapter(ReActPolicy())

        max_iterations = kwargs.get("max_iterations", 50)
        iteration = 0
        self._current_step = 0
        self._total_steps = max_iterations  # Estimate, will be updated as we go

        # Emit initial progress
        self._emit_progress(trace, "initialization")

        while iteration < max_iterations:
            # Check for cancellation
            if self._cancellation_token:
                raise asyncio.CancelledError("Agent execution cancelled")

            # Update state with current iteration
            state["iteration"] = iteration
            self._current_step = iteration

            # Get next steps from policy
            steps = await policy.next_steps(agent, messages, state)

            if not steps:
                # No more steps, finalize
                if messages and messages[-1].role == MessageRole.ASSISTANT:
                    output_message = messages[-1]
                else:
                    # Generate final response
                    final_response = await self._call_model(agent, messages, trace, stream=False)
                    assert isinstance(final_response, ModelResponse), (
                        "Expected ModelResponse when stream=False"
                    )
                    output_message = Message.assistant(final_response.content)
                    messages.append(output_message)
                break

            # Update total steps estimate if we have more steps
            if len(steps) > 0:
                self._total_steps = max(self._total_steps, iteration + len(steps))

            # Emit progress before executing steps
            step_type = steps[0].step_type if steps else None
            self._emit_progress(trace, step_type)

            # Execute steps (potentially in parallel)
            step_results = await self._execute_steps_parallel(steps, agent, trace)

            # Process step results
            final_output_message: Message | None = None
            last_model_response: ModelResponse | None = None
            for step_result in step_results:
                if step_result.step_type == "final":
                    if step_result.output_data and "output" in step_result.output_data:
                        final_output_message = step_result.output_data["output"]
                    break
                if step_result.step_type == "model_call":
                    # Handle model response
                    if (
                        step_result.output_data
                        and isinstance(step_result.output_data, dict)
                        and "response" in step_result.output_data
                    ):
                        response_data = step_result.output_data.get("response", {})
                        content = (
                            response_data.get("content", "")
                            if isinstance(response_data, dict)
                            else ""
                        )
                        tool_calls_data = (
                            response_data.get("tool_calls", [])
                            if isinstance(response_data, dict)
                            else []
                        )
                        last_model_response = ModelResponse(
                            content=content,
                            tool_calls=None,
                            usage=None,
                        )

                        # Create assistant message with tool calls
                        tool_calls: list[dict[str, Any]] | None = None
                        if tool_calls_data and isinstance(tool_calls_data, list):
                            # Filter and validate tool calls
                            tool_calls = [
                                {
                                    "id": str(tc.get("id", "")) if isinstance(tc, dict) else "",
                                    "name": str(tc.get("name", "")) if isinstance(tc, dict) else "",
                                    "arguments": tc.get("arguments", {})
                                    if isinstance(tc, dict)
                                    and isinstance(tc.get("arguments"), dict)
                                    else {},
                                }
                                for tc in tool_calls_data
                                if isinstance(tc, dict)
                                and tc.get("name")  # Only include valid tool calls with names
                            ]
                            # Set to None if empty after filtering
                            if not tool_calls:
                                tool_calls = None

                        messages.append(Message.assistant(content, tool_calls=tool_calls))

                elif step_result.step_type == "tool_call":
                    # Handle tool call result
                    if step_result.output_data and "result" in step_result.output_data:
                        tool_name = (
                            step_result.input_data.get("tool_name", "")
                            if step_result.input_data
                            else ""
                        )
                        tool_call_id = (
                            step_result.input_data.get("tool_call_id", "")
                            if step_result.input_data
                            else ""
                        )
                        tool_result = step_result.output_data["result"]

                        # Add tool result message (tool_call_id required by OpenAI API)
                        messages.append(
                            Message.tool(
                                f"Tool {tool_name} executed",
                                {
                                    "result": tool_result,
                                    "tool": tool_name,
                                    "tool_call_id": tool_call_id,
                                },
                            )
                        )

                elif step_result.step_type == "subagent_call":
                    # Handle sub-agent call result (for supervisor policy)
                    if (
                        step_result.output_data
                        and isinstance(step_result.output_data, dict)
                        and "result" in step_result.output_data
                    ):
                        subagent_name = (
                            step_result.input_data.get("agent_name", "")
                            if step_result.input_data
                            else ""
                        )
                        subagent_result = step_result.output_data.get("result")

                        # Add sub-agent result message
                        if subagent_result is not None:
                            # Convert result to string for message content
                            if isinstance(subagent_result, str):
                                result_content = subagent_result
                            elif isinstance(subagent_result, dict) and "content" in subagent_result:
                                result_content = str(subagent_result["content"])
                            elif hasattr(subagent_result, "content"):
                                result_content = str(subagent_result.content)
                            else:
                                result_content = str(subagent_result)

                            messages.append(
                                Message.assistant(
                                    f"Sub-agent {subagent_name} completed: {result_content}"
                                )
                            )

                            # Update state for supervisor policy
                            state["subagent_result"] = {
                                "agent": subagent_name,
                                "output": subagent_result,
                                "trace_id": step_result.output_data.get("trace_id"),
                            }
                            state["waiting_for_subagent"] = False

            # Let policy reflect on step results (e.g. PlanExecutePolicy updates phase/plan)
            if (
                last_model_response is not None
                and hasattr(policy, "reflect")
                and callable(policy.reflect)
            ):
                state.setdefault(
                    "phase", "planning"
                )  # so policies can detect first (planning) phase
                observation = {"result": last_model_response}
                reflected = await policy.reflect(state, observation)
                if isinstance(reflected, dict):
                    state.update(reflected)

            if final_output_message is not None:
                output_message = final_output_message
                break

            iteration += 1

        # Finalize if we hit max iterations
        if iteration >= max_iterations:
            if messages and messages[-1].role == MessageRole.ASSISTANT:
                output_message = messages[-1]
            else:
                final_response = await self._call_model(agent, messages, trace, stream=False)
                assert isinstance(final_response, ModelResponse), (
                    "Expected ModelResponse when stream=False"
                )
                output_message = Message.assistant(final_response.content)
                messages.append(output_message)

        # Import here to avoid circular import
        from routekitai.core.agent import RunResult

        return RunResult(
            output=output_message,
            trace_id=trace.trace_id,
            final_state=state,
            messages=messages,
        )

    async def _execute_steps_parallel(
        self, steps: list[Step], agent: "Agent", trace: Trace
    ) -> list[Step]:
        """Execute steps in parallel with concurrency control.

        Args:
            steps: Steps to execute
            agent: Agent instance
            trace: Trace for recording

        Returns:
            List of completed steps with outputs (may include steps with errors)

        Note:
            If a step fails, it will have step.error set and the exception will be
            captured. Other steps will continue executing. The first error will be
            raised after all steps complete.
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [self._execute_step(step, agent, trace, semaphore) for step in steps]
        # Use return_exceptions=True to collect all results, even if some fail
        results: list[Step | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to steps with errors
        completed_steps: list[Step] = []
        first_error: BaseException | None = None

        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                # Create a step with error
                step = steps[i]
                step.error = str(result)
                step.output_data = None
                completed_steps.append(step)
                if first_error is None:
                    first_error = result
            elif isinstance(result, Step):
                completed_steps.append(result)
            else:
                # Unexpected type - wrap in error
                step = steps[i]
                step.error = f"Unexpected result type: {type(result).__name__}"
                step.output_data = None
                completed_steps.append(step)
                if first_error is None:
                    first_error = RuntimeError(f"Unexpected result type: {type(result).__name__}")

        # Raise first error if any occurred
        if first_error:
            raise first_error

        return completed_steps

    async def _execute_step(
        self, step: Step, agent: "Agent", trace: Trace, semaphore: asyncio.Semaphore
    ) -> Step:
        """Execute a single step.

        Args:
            step: Step to execute
            agent: Agent instance
            trace: Trace for recording
            semaphore: Semaphore for concurrency control

        Returns:
            Completed step with output
        """
        async with semaphore:
            start_time = time.time()

            # Add step_started event for trace completeness
            trace.add_event(
                "step_started",
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "input_data": step.input_data,
                },
            )

            try:
                if step.step_type == "final":
                    # Policy produced a final output (e.g. GraphPolicy); pass it through
                    step.output_data = {"output": step.input_data.get("output")}
                elif step.step_type == "model_call":
                    # Check if in replay mode
                    if self._replay_mode and self._replay_trace:
                        # Match by sequential order using step_completed events
                        # Find the next step_completed event of type model_call
                        model_call_count = len(
                            [s for s in self._replay_step_index_history if s == "model_call"]
                        )
                        matching_step_event = None
                        step_count = 0
                        for step_event in self._replay_step_events:
                            if step_event.data.get("step_type") == "model_call":
                                if step_count == model_call_count:
                                    matching_step_event = step_event
                                    break
                                step_count += 1

                        if matching_step_event:
                            # Find the corresponding model_called event by step_id
                            step_id = matching_step_event.data.get("step_id")
                            matching_event = next(
                                (
                                    e
                                    for e in self._replay_model_events
                                    if e.data.get("step_id") == step_id
                                ),
                                None,
                            )
                            if not matching_event and model_call_count < len(
                                self._replay_model_events
                            ):
                                # Fallback: use sequential order
                                matching_event = self._replay_model_events[model_call_count]
                        elif model_call_count < len(self._replay_model_events):
                            # Fallback: use sequential order
                            matching_event = self._replay_model_events[model_call_count]
                        else:
                            raise ReplayMismatchError(
                                f"Replay mismatch: expected model call at index {model_call_count}, "
                                f"but only {len(self._replay_model_events)} model call events in trace",
                                context={
                                    "step_id": step.step_id,
                                    "trace_id": trace.trace_id,
                                    "expected_index": model_call_count,
                                    "available_events": len(self._replay_model_events),
                                },
                            )

                        if not matching_event:
                            raise ReplayMismatchError(
                                "Replay mismatch: could not find matching model call event",
                                context={
                                    "step_id": step.step_id,
                                    "trace_id": trace.trace_id,
                                    "model_call_count": model_call_count,
                                },
                            )

                        self._replay_step_index_history.append("model_call")
                        response_data = matching_event.data.get("response", {})
                    else:
                        # Call model (check cancellation)
                        if self._cancellation_token:
                            raise asyncio.CancelledError("Model call cancelled")
                        # Validate and extract messages
                        messages_data = step.input_data.get("messages", [])
                        if not isinstance(messages_data, list):
                            raise RouteKitRuntimeError(
                                f"Invalid messages data in step: expected list, got {type(messages_data).__name__}",
                                context={"step_id": step.step_id, "step_type": step.step_type},
                            )
                        # Convert dict messages to Message objects if needed (optimize: avoid conversion if already Message)
                        messages: list[Message] = []
                        for msg_data in messages_data:
                            if isinstance(msg_data, Message):
                                messages.append(msg_data)
                            elif isinstance(msg_data, dict):
                                try:
                                    messages.append(Message(**msg_data))
                                except Exception as e:
                                    raise RouteKitRuntimeError(
                                        f"Invalid message format in step: {e}",
                                        context={
                                            "step_id": step.step_id,
                                            "step_type": step.step_type,
                                            "message_data": str(msg_data)[:100],
                                        },
                                    ) from e
                            else:
                                raise RouteKitRuntimeError(
                                    f"Invalid message format in step: expected Message or dict, got {type(msg_data).__name__}",
                                    context={"step_id": step.step_id, "step_type": step.step_type},
                                )
                        response = await self._call_model(agent, messages, trace, stream=False)
                        assert isinstance(response, ModelResponse), (
                            "Expected ModelResponse when stream=False"
                        )
                        response_data = {
                            "content": response.content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                }
                                for tc in (response.tool_calls or [])
                            ],
                            "usage": response.usage.model_dump() if response.usage else None,
                        }

                    step.output_data = {"response": response_data}
                    trace.add_event(
                        "model_called",
                        {
                            "step_id": step.step_id,
                            "response": response_data,
                        },
                    )

                elif step.step_type == "tool_call":
                    # Check if in replay mode for tool calls
                    if self._replay_mode and self._replay_trace:
                        # Match tool calls by sequential order
                        tool_call_index = len(
                            [s for s in self._replay_step_index_history if s == "tool_call"]
                        )
                        if tool_call_index >= len(self._replay_tool_call_events):
                            raise ReplayMismatchError(
                                f"Replay mismatch: expected tool call at index {tool_call_index}, "
                                f"but only {len(self._replay_tool_call_events)} tool call events in trace",
                                context={
                                    "step_id": step.step_id,
                                    "trace_id": trace.trace_id,
                                    "tool_name": step.input_data.get("tool_name", "unknown"),
                                    "expected_index": tool_call_index,
                                },
                            )
                        matching_call = self._replay_tool_call_events[tool_call_index]
                        tool_name = matching_call.data.get("tool", "")

                        # Match tool result by sequential order (tool results should be in same order as tool calls)
                        if tool_call_index >= len(self._replay_tool_result_events):
                            # No result available - might be an error case
                            tool_result = ""
                        else:
                            matching_result = self._replay_tool_result_events[tool_call_index]
                            tool_result = matching_result.data.get("result", "")

                        step.output_data = {"result": tool_result}
                        # Track that we processed a tool call
                        self._replay_step_index_history.append("tool_call")
                    else:
                        tool_name = step.input_data.get("tool_name")
                        tool_args = step.input_data.get("tool_args", {})

                        # Validate tool_name
                        if not tool_name:
                            raise RouteKitRuntimeError(
                                "Missing tool_name in step input_data",
                                context={"step_id": step.step_id, "step_type": step.step_type},
                            )
                        if not isinstance(tool_args, dict):
                            raise RouteKitRuntimeError(
                                f"Invalid tool_args in step: expected dict, got {type(tool_args).__name__}",
                                context={
                                    "step_id": step.step_id,
                                    "step_type": step.step_type,
                                    "tool_name": tool_name,
                                },
                            )

                        # Find tool
                        tool = next((t for t in agent.tools if t.name == tool_name), None)
                        if not tool:
                            step.error = f"Tool {tool_name} not found"
                            raise ToolError(
                                f"Tool '{tool_name}' not found in agent '{agent.name}'",
                                context={
                                    "agent_name": agent.name,
                                    "tool_name": tool_name,
                                    "step_id": step.step_id,
                                },
                            )

                        # Execute tool (pass agent for agent-level filters)
                        try:
                            tool_result = await self._execute_tool(
                                tool, tool_args, trace, step.step_id, agent=agent
                            )
                            step.output_data = {"result": tool_result}
                        except ToolError as e:
                            # Wrap ToolError from tool filters/approval gates in RouteKitRuntimeError for consistency
                            error_msg = str(e)
                            if (
                                "not allowed" in error_msg
                                or "filtered" in error_msg
                                or "requires approval" in error_msg
                                or "blocked" in error_msg
                            ):
                                raise RouteKitRuntimeError(
                                    error_msg, context=getattr(e, "context", {})
                                ) from e
                            raise

                elif step.step_type == "subagent_call":
                    # Execute sub-agent (for supervisor policy)
                    subagent_name = step.input_data.get("agent_name")
                    prompt = step.input_data.get("prompt", "")

                    # Validate subagent_name
                    if not subagent_name:
                        raise RouteKitRuntimeError(
                            "Missing agent_name in subagent_call step",
                            context={"step_id": step.step_id, "step_type": step.step_type},
                        )

                    if subagent_name not in self.agents:
                        raise RouteKitRuntimeError(
                            f"Sub-agent '{subagent_name}' not found",
                            context={
                                "step_id": step.step_id,
                                "step_type": step.step_type,
                                "agent_name": subagent_name,
                            },
                        )

                    # Execute sub-agent
                    subagent_result = await self.run(subagent_name, prompt)
                    step.output_data = {
                        "result": subagent_result.output.content,
                        "trace_id": subagent_result.trace_id,
                        "messages": [m.model_dump() for m in subagent_result.messages],
                    }

                trace.add_event(
                    "step_completed",
                    {
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "latency_ms": (time.time() - start_time) * 1000,
                    },
                )

            except (RouteKitRuntimeError, ToolError, ModelError, asyncio.CancelledError) as e:
                # Re-raise known errors
                step.error = str(e)
                trace.add_event(
                    "error",
                    {
                        "step_id": step.step_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "context": getattr(e, "context", {}),
                    },
                )
                raise
            except Exception as e:
                # Wrap unknown exceptions, preserving context
                step.error = str(e)
                error_context = {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                }
                # Preserve context from original exception if available
                if hasattr(e, "context") and isinstance(e.context, dict):
                    error_context.update(e.context)

                trace.add_event(
                    "error",
                    {
                        "step_id": step.step_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "context": error_context,
                    },
                )
                raise RouteKitRuntimeError(
                    f"Step execution failed: {e}", context=error_context
                ) from e

            finally:
                step.latency_ms = (time.time() - start_time) * 1000

            return step

    async def _call_model(
        self,
        agent: "Agent",
        messages: list[Message],
        trace: Trace,
        stream: bool = False,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Call the agent's model.

        Args:
            agent: Agent instance
            messages: Messages to send
            trace: Trace for recording
            stream: Whether to stream the response

        Returns:
            Model response or stream of events
        """
        start_time = time.time()
        try:
            response = await agent.model.chat(messages, tools=agent.tools, stream=stream)
            latency_ms = (time.time() - start_time) * 1000

            if stream:
                # Return streaming iterator
                assert isinstance(response, AsyncIterator), (
                    "Expected AsyncIterator when stream=True"
                )

                async def stream_wrapper() -> AsyncIterator[StreamEvent]:
                    content_buffer = ""
                    tool_calls_buffer: list[dict[str, Any]] = []
                    usage = None

                    async for event in response:
                        # Forward stream events to trace
                        if event.content:
                            content_buffer += event.content or ""
                        if event.tool_calls:
                            tool_calls_buffer.extend(
                                [
                                    {
                                        "id": tc.id,
                                        "name": tc.name,
                                        "arguments": tc.arguments,
                                    }
                                    for tc in (event.tool_calls or [])
                                ]
                            )
                        if event.usage:
                            usage = event.usage

                        # Emit streaming event to trace
                        trace.add_event(
                            "model_stream_chunk",
                            {
                                "model": agent.model.name,
                                "chunk": event.content or "",
                                "event_type": event.type,
                            },
                        )

                        yield event

                    # Emit final model_called event with complete response
                    trace.add_event(
                        "model_called",
                        {
                            "model": agent.model.name,
                            "messages_count": len(messages),
                            "response": {
                                "content": content_buffer,
                                "tool_calls": tool_calls_buffer,
                                "usage": usage.model_dump() if usage else None,
                            },
                            "latency_ms": latency_ms,
                            "streamed": True,
                        },
                    )

                return stream_wrapper()

            # Non-streaming mode
            if not isinstance(response, ModelResponse):
                raise ModelError("Model returned a stream when stream=False was requested")

            trace.add_event(
                "model_called",
                {
                    "model": agent.model.name,
                    "messages_count": len(messages),
                    "response": {
                        "content": response.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                            for tc in (response.tool_calls or [])
                        ],
                        "usage": response.usage.model_dump() if response.usage else None,
                    },
                    "latency_ms": latency_ms,
                },
            )

            return response
        except (ModelError, asyncio.CancelledError) as e:
            # Re-raise model errors and cancellations
            trace.add_event(
                "error",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "context": {"model": agent.model.name, "context": "model_call"},
                },
            )
            raise
        except Exception as e:
            # Wrap unknown exceptions
            trace.add_event(
                "error",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "context": {"model": agent.model.name, "context": "model_call"},
                },
            )
            raise ModelError(
                f"Model call failed: {e}",
                context={"model": agent.model.name, "error_type": type(e).__name__},
            ) from e

    async def _execute_tool(
        self,
        tool: Tool,
        tool_args: dict[str, Any],
        trace: Trace,
        step_id: str | None = None,
        agent: "Agent | None" = None,
    ) -> Any:
        """Execute a tool with permission checks, retries, and timeout.

        Args:
            tool: Tool to execute
            tool_args: Tool arguments
            trace: Trace for recording
            step_id: Optional step ID
            agent: Optional agent instance (for agent-level filters)

        Returns:
            Tool execution result

        Raises:
            ToolError: If tool execution fails
        """
        # Check tool filter (allow/deny list) - agent level first, then runtime level
        # Agent-level filter takes precedence - if agent has a filter, only check that
        if agent and agent.tool_filter:
            if not agent.tool_filter.is_allowed(tool.name):
                error_msg = f"Tool {tool.name} is not allowed (filtered by agent policy)"
                trace.add_event(
                    "tool_called",
                    {
                        "tool": tool.name,
                        "step_id": step_id,
                        "error": error_msg,
                    },
                )
                raise ToolError(
                    error_msg,
                    context={"tool_name": tool.name, "step_id": step_id, "filter_level": "agent"},
                )
        # Runtime-level filter (only checked if agent doesn't have a filter)
        elif self.policy_hooks and self.policy_hooks.tool_filter:
            if not self.policy_hooks.tool_filter.is_allowed(tool.name):
                error_msg = f"Tool {tool.name} is not allowed (filtered by runtime policy)"
                trace.add_event(
                    "tool_called",
                    {
                        "tool": tool.name,
                        "step_id": step_id,
                        "error": error_msg,
                    },
                )
                raise ToolError(
                    error_msg,
                    context={"tool_name": tool.name, "step_id": step_id, "filter_level": "agent"},
                )

        # Check approval gate
        if self.policy_hooks and self.policy_hooks.approval_gate:
            # Convert ToolPermission enum to strings for approval gate
            permission_strings = [
                p.value if hasattr(p, "value") else str(p) for p in (tool.permissions or [])
            ]
            if self.policy_hooks.approval_gate.requires_approval(
                tool.name, tool_args, permission_strings
            ):
                if not self.policy_hooks.approval_gate.is_approved(tool.name, tool_args):
                    error_msg = f"Tool {tool.name} requires approval (blocked by approval gate)"
                    trace.add_event(
                        "tool_called",
                        {
                            "tool": tool.name,
                            "step_id": step_id,
                            "error": error_msg,
                        },
                    )
                    raise ToolError(
                        error_msg,
                        context={
                            "tool_name": tool.name,
                            "step_id": step_id,
                            "filter_level": "agent",
                        },
                    )

        # Check permissions
        if self.permission_manager:
            # Check if tool requires permissions
            if tool.permissions:
                # Check each required permission
                for perm in tool.permissions:
                    if not self.permission_manager.check_permission(perm, tool.name):
                        error_msg = f"Permission denied for tool {tool.name} (requires {perm})"
                        trace.add_event(
                            "tool_called",
                            {
                                "tool": tool.name,
                                "step_id": step_id,
                                "error": error_msg,
                            },
                        )
                        raise ToolError(
                            error_msg,
                            context={
                                "tool_name": tool.name,
                                "step_id": step_id,
                                "filter_level": "agent",
                            },
                        )

        # Redact sensitive fields before logging
        redacted_args = tool.redact_data(tool_args)

        # Apply PII redaction hook if configured
        if self.policy_hooks and self.policy_hooks.pii_redaction:
            redacted_args = self.policy_hooks.pii_redaction.redact_dict(redacted_args)

        trace.add_event(
            "tool_called",
            {
                "tool": tool.name,
                "arguments": redacted_args,
                "step_id": step_id,
            },
        )

        start_time = time.time()
        timeout = tool.timeout or self.timeout

        # Retry logic with exponential backoff
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                # Check for cancellation
                if self._cancellation_token:
                    raise asyncio.CancelledError("Tool execution cancelled")

                if timeout:
                    result = await asyncio.wait_for(tool.execute(**tool_args), timeout=timeout)
                else:
                    result = await tool.execute(**tool_args)

                latency_ms = (time.time() - start_time) * 1000
                trace.add_event(
                    "tool_result",
                    {
                        "tool": tool.name,
                        "result": str(result),
                        "step_id": step_id,
                        "latency_ms": latency_ms,
                    },
                )

                return result

            except asyncio.CancelledError:
                # Don't retry on cancellation
                raise
            except TimeoutError as e:
                last_error = e
                if attempt < self.max_retries:
                    # Exponential backoff: base * (2^attempt), capped at max
                    backoff_delay = min(
                        self.retry_backoff_base * (2**attempt), self.retry_backoff_max
                    )
                    await asyncio.sleep(backoff_delay)
                    continue
                raise ToolError(
                    f"Tool '{tool.name}' timed out after {timeout}s",
                    context={"tool_name": tool.name, "timeout": timeout, "step_id": step_id},
                ) from e
            except ToolError as e:
                # Retry ToolError from execution failures (not validation/permission errors)
                # Check if it's a retryable error by examining the message
                error_msg = str(e).lower()
                is_retryable = (
                    (
                        "execution failed" in error_msg
                        or "intentional failure" in error_msg
                        or "failed:" in error_msg
                    )
                    and "validation" not in error_msg
                    and "permission" not in error_msg
                )

                if is_retryable and attempt < self.max_retries:
                    last_error = e
                    # Exponential backoff
                    backoff_delay = min(
                        self.retry_backoff_base * (2**attempt), self.retry_backoff_max
                    )
                    await asyncio.sleep(backoff_delay)
                    continue
                # Don't retry validation/permission errors or if retries exhausted
                raise
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    # Exponential backoff
                    backoff_delay = min(
                        self.retry_backoff_base * (2**attempt), self.retry_backoff_max
                    )
                    await asyncio.sleep(backoff_delay)
                    continue
                # Wrap unknown exceptions in ToolError
                raise ToolError(
                    f"Tool {tool.name} failed: {e}",
                    context={"tool_name": tool.name, "attempt": attempt + 1, "step_id": step_id},
                ) from e

        raise ToolError(
            f"Tool {tool.name} failed after {self.max_retries} retries",
            context={"tool_name": tool.name, "max_retries": self.max_retries, "step_id": step_id},
        ) from last_error

    async def replay(
        self,
        trace_id: str,
        agent_name: str,
        verify_output: bool = True,
        strict: bool = True,
    ) -> "RunResult":
        """Replay a trace with deterministic execution.

        This method loads a trace file and re-executes the agent run using
        the recorded model responses and tool results. This enables:
        - Deterministic testing of agent behavior
        - Debugging failed runs
        - Reproducing issues in production

        Args:
            trace_id: Trace ID to replay
            agent_name: Agent name to use for replay (must match original agent)
            verify_output: If True, verify replay output matches original
            strict: If True, raise ReplayMismatchError on any mismatch

        Returns:
            RunResult from replay

        Raises:
            RouteKitRuntimeError: If trace not found or agent mismatch
            ReplayMismatchError: If replay encounters a mismatch and strict=True
        """
        if agent_name not in self.agents:
            raise RouteKitRuntimeError(f"Agent {agent_name} not found")

        # Load trace
        if not self.trace_dir:
            raise RouteKitRuntimeError(
                "trace_dir must be set for replay",
                context={"trace_id": trace_id, "agent_name": agent_name},
            )

        exporter = JSONLExporter(output_dir=self.trace_dir)
        trace = await exporter.load(trace_id)
        if not trace:
            raise RouteKitRuntimeError(
                f"Trace {trace_id} not found",
                context={"trace_id": trace_id, "trace_dir": str(self.trace_dir)},
            )

        # Verify agent matches original
        run_started = trace.get_events_by_type("run_started")
        if run_started:
            original_agent = run_started[0].data.get("agent", "")
            if original_agent and original_agent != agent_name:
                if strict:
                    raise ReplayMismatchError(
                        f"Agent mismatch: trace was for '{original_agent}', "
                        f"replay requested '{agent_name}'"
                    )

        # Set replay mode
        self._replay_mode = True
        self._replay_trace = trace
        self._replay_step_index = 0
        self._replay_step_index_history: list[str] = []  # Track step types for sequential matching
        # Build ordered lists of events by type for sequential matching
        self._replay_model_events = trace.get_events_by_type("model_called")
        self._replay_tool_call_events = trace.get_events_by_type("tool_called")
        self._replay_tool_result_events = trace.get_events_by_type("tool_result")
        # Build step_completed events in order for unified step matching
        self._replay_step_events = [e for e in trace.events if e.type == "step_completed"]

        try:
            # Extract prompt from trace
            if not run_started:
                raise RouteKitRuntimeError(
                    "Trace missing run_started event", context={"trace_id": trace_id}
                )
            prompt = run_started[0].data.get("prompt", "")

            # Replay execution
            agent = self.agents[agent_name]
            result = await self._execute_steps(agent, prompt, trace, None)

            # Verify output if requested
            if verify_output:
                run_completed = trace.get_events_by_type("run_completed")
                if run_completed:
                    original_result = run_completed[0].data.get("result", {})
                    original_output = original_result.get("output", {}).get("content", "")
                    if original_output != result.output.content:
                        error_msg = (
                            f"Output mismatch: original='{original_output}', "
                            f"replay='{result.output.content}'"
                        )
                        if strict:
                            raise ReplayMismatchError(
                                error_msg,
                                context={
                                    "trace_id": trace_id,
                                    "original_output": original_output,
                                    "replay_output": result.output.content,
                                },
                            )
                        else:
                            # Log warning but continue
                            trace.add_event("replay_warning", {"message": error_msg})

            return result

        finally:
            self._replay_mode = False
            self._replay_trace = None
            self._replay_step_index = 0
            self._replay_step_index_history = []
            self._replay_model_events = []
            self._replay_tool_call_events = []
            self._replay_tool_result_events = []


class DefaultPolicy(Policy):
    """Default policy for simple agent execution."""

    async def next_steps(
        self,
        agent: "Agent",
        messages: list[Message],
        state: dict[str, Any],
    ) -> list[Step]:
        """Default policy: call model, then execute any tool calls.

        Args:
            agent: Agent instance
            messages: Current messages
            state: Current state

        Returns:
            List of steps
        """
        # Check if we need to call model
        if not messages or messages[-1].role != MessageRole.ASSISTANT:
            # Call model
            return [
                Step(
                    step_id=str(uuid.uuid4()),
                    step_type="model_call",
                    input_data={"messages": [m.model_dump() for m in messages]},
                )
            ]

        # Check for tool calls in last message
        last_message = messages[-1]
        if last_message.tool_calls:
            # Execute tool calls
            steps = []
            for tool_call in last_message.tool_calls:
                steps.append(
                    Step(
                        step_id=str(uuid.uuid4()),
                        step_type="tool_call",
                        input_data={
                            "tool_name": tool_call["name"],
                            "tool_args": tool_call.get("arguments", {}),
                            "tool_call_id": tool_call.get("id", ""),
                        },
                    )
                )
            return steps

        # No more steps
        return []
