"""Trace analysis and metrics calculation."""

from typing import Any

from pydantic import BaseModel, Field

from routekitai.observability.trace import Trace, TraceEvent


class TraceMetrics(BaseModel):
    """Metrics calculated from a trace."""

    model_config = {"protected_namespaces": ()}

    total_events: int = Field(..., description="Total number of events")
    total_duration_ms: float = Field(..., description="Total execution duration in milliseconds")
    model_calls: int = Field(..., description="Number of model calls")
    tool_calls: int = Field(..., description="Number of tool calls")
    errors: int = Field(..., description="Number of errors")
    total_tokens: int = Field(default=0, description="Total tokens used (prompt + completion)")
    prompt_tokens: int = Field(default=0, description="Prompt tokens")
    completion_tokens: int = Field(default=0, description="Completion tokens")
    avg_model_latency_ms: float = Field(default=0.0, description="Average model call latency")
    avg_tool_latency_ms: float = Field(default=0.0, description="Average tool call latency")
    error_rate: float = Field(default=0.0, description="Error rate (0.0 to 1.0)")
    steps: int = Field(default=0, description="Number of execution steps")


class TraceAnalyzer:
    """Analyzes traces and calculates metrics."""

    @staticmethod
    def analyze(trace: Trace) -> TraceMetrics:
        """Analyze a trace and calculate metrics.

        Args:
            trace: Trace to analyze

        Returns:
            Calculated metrics
        """
        if not trace.events:
            return TraceMetrics(
                total_events=0,
                total_duration_ms=0.0,
                model_calls=0,
                tool_calls=0,
                errors=0,
            )

        # Find start and end times
        start_time = trace.events[0].timestamp
        end_time = trace.events[-1].timestamp
        total_duration_ms = (end_time - start_time) * 1000

        # Count events
        model_calls = 0
        tool_calls = 0
        errors = 0
        steps = 0

        # Token usage
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0

        # Latency tracking
        model_latencies: list[float] = []
        tool_latencies: list[float] = []

        # Track step start times
        step_start_times: dict[str, float] = {}

        for event in trace.events:
            if event.type == "model_called":
                model_calls += 1
                # Extract token usage if available
                if "usage" in event.data:
                    usage = event.data["usage"]
                    if isinstance(usage, dict):
                        total_tokens += usage.get("total_tokens", 0)
                        prompt_tokens += usage.get("prompt_tokens", 0)
                        completion_tokens += usage.get("completion_tokens", 0)
            elif event.type == "tool_called":
                tool_calls += 1
                # Track tool call start time
                step_id = event.data.get("step_id", "")
                if step_id:
                    step_start_times[step_id] = event.timestamp
            elif event.type == "tool_result":
                # Calculate tool latency
                step_id = event.data.get("step_id", "")
                if step_id and step_id in step_start_times:
                    latency_ms = (event.timestamp - step_start_times[step_id]) * 1000
                    tool_latencies.append(latency_ms)
                    del step_start_times[step_id]
            elif event.type == "error":
                errors += 1
            elif event.type == "step_started":
                steps += 1
                step_id = event.data.get("step_id", "")
                if step_id:
                    step_start_times[step_id] = event.timestamp
            elif event.type == "step_completed":
                # Calculate step latency (could be model or tool)
                step_id = event.data.get("step_id", "")
                if step_id and step_id in step_start_times:
                    latency_ms = (event.timestamp - step_start_times[step_id]) * 1000
                    # Check if this was a model call step
                    step_type = event.data.get("step_type", "")
                    if step_type == "model_call":
                        model_latencies.append(latency_ms)
                    elif step_type == "tool_call":
                        if latency_ms not in tool_latencies:  # Avoid double counting
                            tool_latencies.append(latency_ms)
                    del step_start_times[step_id]

        # Calculate averages
        avg_model_latency_ms = (
            sum(model_latencies) / len(model_latencies) if model_latencies else 0.0
        )
        avg_tool_latency_ms = sum(tool_latencies) / len(tool_latencies) if tool_latencies else 0.0

        # Calculate error rate
        total_operations = model_calls + tool_calls
        error_rate = errors / total_operations if total_operations > 0 else 0.0

        return TraceMetrics(
            total_events=len(trace.events),
            total_duration_ms=total_duration_ms,
            model_calls=model_calls,
            tool_calls=tool_calls,
            errors=errors,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            avg_model_latency_ms=avg_model_latency_ms,
            avg_tool_latency_ms=avg_tool_latency_ms,
            error_rate=error_rate,
            steps=steps,
        )

    @staticmethod
    def query(
        trace: Trace,
        event_type: str | None = None,
        filter_func: Any | None = None,
    ) -> list[TraceEvent]:
        """Query trace events.

        Args:
            trace: Trace to query
            event_type: Optional event type filter
            filter_func: Optional function to filter events (takes TraceEvent, returns bool)

        Returns:
            List of matching events
        """
        events = trace.events

        if event_type:
            events = [e for e in events if e.type == event_type]

        if filter_func:
            events = [e for e in events if filter_func(e)]

        return events

    @staticmethod
    def search(
        trace: Trace,
        query: str,
        search_in_data: bool = True,
    ) -> list[TraceEvent]:
        """Search trace events by text.

        Args:
            trace: Trace to search
            query: Search query (case-insensitive)
            search_in_data: Whether to search in event data

        Returns:
            List of matching events
        """
        query_lower = query.lower()
        results: list[TraceEvent] = []

        for event in trace.events:
            # Search in event type
            if query_lower in event.type.lower():
                results.append(event)
                continue

            # Search in event data
            if search_in_data:
                if _search_in_dict(event.data, query_lower):
                    results.append(event)

        return results

    @staticmethod
    def get_timeline(trace: Trace) -> list[dict[str, Any]]:
        """Get timeline of events with relative timestamps.

        Args:
            trace: Trace to analyze

        Returns:
            List of timeline entries with relative time and duration
        """
        if not trace.events:
            return []

        start_time = trace.events[0].timestamp
        timeline: list[dict[str, Any]] = []

        for i, event in enumerate(trace.events):
            relative_time_ms = (event.timestamp - start_time) * 1000

            # Calculate duration if this is a completion event
            duration_ms = 0.0
            if event.type in ("step_completed", "tool_result", "model_called"):
                # Look for corresponding start event
                step_id = event.data.get("step_id", "")
                if step_id:
                    # Find the start event
                    for prev_event in reversed(trace.events[:i]):
                        if (
                            prev_event.type in ("step_started", "tool_called", "model_called")
                            and prev_event.data.get("step_id") == step_id
                        ):
                            duration_ms = (event.timestamp - prev_event.timestamp) * 1000
                            break

            timeline.append(
                {
                    "event": event,
                    "relative_time_ms": relative_time_ms,
                    "duration_ms": duration_ms,
                    "index": i,
                }
            )

        return timeline

    @staticmethod
    def get_step_sequence(trace: Trace) -> list[dict[str, Any]]:
        """Get step-by-step execution sequence.

        Args:
            trace: Trace to analyze

        Returns:
            List of steps with their events
        """
        steps: dict[str, dict[str, Any]] = {}
        step_order: list[str] = []

        for event in trace.events:
            step_id = event.data.get("step_id", "")
            if not step_id:
                continue

            if step_id not in steps:
                steps[step_id] = {
                    "step_id": step_id,
                    "step_type": event.data.get("step_type", ""),
                    "events": [],
                    "start_time": event.timestamp,
                    "end_time": None,
                    "duration_ms": 0.0,
                    "error": None,
                }
                step_order.append(step_id)

            steps[step_id]["events"].append(event)

            if event.type == "step_completed":
                steps[step_id]["end_time"] = event.timestamp
                steps[step_id]["duration_ms"] = (
                    event.timestamp - steps[step_id]["start_time"]
                ) * 1000
                if "error" in event.data:
                    steps[step_id]["error"] = event.data["error"]
            elif event.type == "error":
                steps[step_id]["error"] = event.data.get("message", "Unknown error")

        return [steps[step_id] for step_id in step_order]


def _search_in_dict(data: dict[str, Any], query: str) -> bool:
    """Recursively search for query in dictionary values.

    Args:
        data: Dictionary to search
        query: Search query (lowercase)

    Returns:
        True if query found
    """
    for key, value in data.items():
        if query in key.lower():
            return True
        if isinstance(value, str) and query in value.lower():
            return True
        if isinstance(value, dict) and _search_in_dict(value, query):
            return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and query in item.lower():
                    return True
                if isinstance(item, dict) and _search_in_dict(item, query):
                    return True
    return False
