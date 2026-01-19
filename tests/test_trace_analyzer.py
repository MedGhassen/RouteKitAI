"""Tests for trace analysis and visualization."""

import time

from routekit.observability.analyzer import TraceAnalyzer, TraceMetrics
from routekit.observability.trace import Trace


def create_test_trace() -> Trace:
    """Create a test trace with various events."""
    trace = Trace(trace_id="test_trace_123", metadata={"agent_name": "test_agent"})

    base_time = time.time()

    # Run started
    trace.add_event("run_started", {"trace_id": "test_trace_123"})

    # Step 1: Model call
    step1_id = "step_1"
    trace.add_event(
        "step_started",
        {"step_id": step1_id, "step_type": "model_call"},
    )
    trace.add_event(
        "model_called",
        {
            "step_id": step1_id,
            "model": "gpt-4",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
    )
    trace.add_event(
        "step_completed",
        {"step_id": step1_id, "step_type": "model_call", "latency_ms": 500.0},
    )

    # Step 2: Tool call
    step2_id = "step_2"
    trace.add_event(
        "step_started",
        {"step_id": step2_id, "step_type": "tool_call"},
    )
    trace.add_event(
        "tool_called",
        {"step_id": step2_id, "tool_name": "echo", "arguments": {"message": "Hello"}},
    )
    trace.add_event(
        "tool_result",
        {"step_id": step2_id, "result": "Hello", "latency_ms": 10.0},
    )
    trace.add_event(
        "step_completed",
        {"step_id": step2_id, "step_type": "tool_call", "latency_ms": 10.0},
    )

    # Step 3: Another model call
    step3_id = "step_3"
    trace.add_event(
        "step_started",
        {"step_id": step3_id, "step_type": "model_call"},
    )
    trace.add_event(
        "model_called",
        {
            "step_id": step3_id,
            "model": "gpt-4",
            "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
        },
    )
    trace.add_event(
        "step_completed",
        {"step_id": step3_id, "step_type": "model_call", "latency_ms": 800.0},
    )

    # Run completed
    trace.add_event("run_completed", {"trace_id": "test_trace_123"})

    # Manually set timestamps for testing
    for i, event in enumerate(trace.events):
        event.timestamp = base_time + (i * 0.1)

    return trace


def create_trace_with_error() -> Trace:
    """Create a test trace with an error."""
    trace = Trace(trace_id="error_trace", metadata={})
    base_time = time.time()

    trace.add_event("run_started", {})
    trace.add_event(
        "step_started",
        {"step_id": "step_1", "step_type": "tool_call"},
    )
    trace.add_event(
        "error",
        {
            "step_id": "step_1",
            "message": "Tool execution failed",
            "error_type": "ToolError",
        },
    )
    trace.add_event("run_completed", {})

    for i, event in enumerate(trace.events):
        event.timestamp = base_time + (i * 0.1)

    return trace


class TestTraceMetrics:
    """Test TraceMetrics model."""

    def test_trace_metrics_creation(self) -> None:
        """Test creating TraceMetrics."""
        metrics = TraceMetrics(
            total_events=10,
            total_duration_ms=1000.0,
            model_calls=2,
            tool_calls=1,
            errors=0,
            total_tokens=450,
            prompt_tokens=300,
            completion_tokens=150,
            avg_model_latency_ms=650.0,
            avg_tool_latency_ms=10.0,
            error_rate=0.0,
            steps=3,
        )

        assert metrics.total_events == 10
        assert metrics.total_duration_ms == 1000.0
        assert metrics.model_calls == 2
        assert metrics.tool_calls == 1
        assert metrics.errors == 0
        assert metrics.total_tokens == 450
        assert metrics.error_rate == 0.0


class TestTraceAnalyzer:
    """Test TraceAnalyzer functionality."""

    def test_analyze_empty_trace(self) -> None:
        """Test analyzing an empty trace."""
        trace = Trace(trace_id="empty", events=[], metadata={})
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        assert metrics.total_events == 0
        assert metrics.total_duration_ms == 0.0
        assert metrics.model_calls == 0
        assert metrics.tool_calls == 0
        assert metrics.errors == 0

    def test_analyze_basic_trace(self) -> None:
        """Test analyzing a basic trace."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        assert metrics.total_events == len(trace.events)
        assert metrics.model_calls == 2
        assert metrics.tool_calls == 1
        assert metrics.steps == 3
        assert metrics.total_tokens == 450  # 150 + 300
        assert metrics.prompt_tokens == 300  # 100 + 200
        assert metrics.completion_tokens == 150  # 50 + 100
        assert metrics.errors == 0
        assert metrics.error_rate == 0.0

    def test_analyze_trace_with_error(self) -> None:
        """Test analyzing a trace with errors."""
        trace = create_trace_with_error()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        assert metrics.errors == 1
        # Error rate should be calculated based on operations
        assert metrics.error_rate >= 0.0

    def test_analyze_latency_calculation(self) -> None:
        """Test that latency is calculated correctly."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        # Should have calculated average latencies
        assert metrics.avg_model_latency_ms >= 0.0
        assert metrics.avg_tool_latency_ms >= 0.0

    def test_query_by_event_type(self) -> None:
        """Test querying events by type."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        model_events = analyzer.query(trace, event_type="model_called")
        assert len(model_events) == 2
        assert all(e.type == "model_called" for e in model_events)

        tool_events = analyzer.query(trace, event_type="tool_called")
        assert len(tool_events) == 1
        assert all(e.type == "tool_called" for e in tool_events)

    def test_query_with_filter_function(self) -> None:
        """Test querying with a custom filter function."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        # Filter events with step_id
        filtered = analyzer.query(
            trace,
            filter_func=lambda e: "step_id" in e.data and e.data["step_id"] == "step_1",
        )
        assert len(filtered) > 0
        assert all("step_id" in e.data for e in filtered)
        assert all(e.data["step_id"] == "step_1" for e in filtered)

    def test_query_combines_filters(self) -> None:
        """Test that query combines event_type and filter_func."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        # Get model calls for step_1
        filtered = analyzer.query(
            trace,
            event_type="model_called",
            filter_func=lambda e: e.data.get("step_id") == "step_1",
        )
        assert len(filtered) == 1
        assert filtered[0].data.get("step_id") == "step_1"

    def test_search_by_text(self) -> None:
        """Test searching traces by text."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        # Search for "echo"
        results = analyzer.search(trace, "echo")
        assert len(results) > 0
        assert any("echo" in str(e.data).lower() for e in results)

        # Search for "gpt-4"
        results = analyzer.search(trace, "gpt-4")
        assert len(results) > 0

    def test_search_case_insensitive(self) -> None:
        """Test that search is case-insensitive."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        results_lower = analyzer.search(trace, "echo")
        results_upper = analyzer.search(trace, "ECHO")
        results_mixed = analyzer.search(trace, "EcHo")

        assert len(results_lower) == len(results_upper) == len(results_mixed)

    def test_search_in_event_type(self) -> None:
        """Test that search includes event types."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        # Search for event type
        results = analyzer.search(trace, "model_called")
        assert len(results) > 0
        assert any(e.type == "model_called" for e in results)

    def test_search_in_nested_data(self) -> None:
        """Test that search works in nested data structures."""
        trace = Trace(trace_id="nested", events=[], metadata={})
        trace.add_event(
            "test_event",
            {
                "nested": {
                    "deep": {"value": "search_me"},
                    "other": "not_this",
                },
            },
        )

        analyzer = TraceAnalyzer()
        results = analyzer.search(trace, "search_me")
        assert len(results) == 1

    def test_get_timeline(self) -> None:
        """Test getting timeline of events."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        timeline = analyzer.get_timeline(trace)
        assert len(timeline) == len(trace.events)

        # First event should have relative_time_ms = 0
        assert timeline[0]["relative_time_ms"] == 0.0

        # Timeline should be ordered
        for i in range(1, len(timeline)):
            assert timeline[i]["relative_time_ms"] >= timeline[i - 1]["relative_time_ms"]

    def test_get_timeline_duration_calculation(self) -> None:
        """Test that timeline calculates durations correctly."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        timeline = analyzer.get_timeline(trace)

        # Find a step_completed event
        completed_events = [entry for entry in timeline if entry["event"].type == "step_completed"]
        if completed_events:
            # Should have duration calculated
            assert completed_events[0]["duration_ms"] >= 0.0

    def test_get_step_sequence(self) -> None:
        """Test getting step-by-step sequence."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        steps = analyzer.get_step_sequence(trace)
        assert len(steps) == 3  # Three steps

        # Each step should have required fields
        for step in steps:
            assert "step_id" in step
            assert "step_type" in step
            assert "events" in step
            assert "start_time" in step
            assert len(step["events"]) > 0

    def test_get_step_sequence_with_duration(self) -> None:
        """Test that step sequence includes duration."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()

        steps = analyzer.get_step_sequence(trace)

        # Steps with completion should have duration
        for step in steps:
            if step.get("end_time") is not None:
                assert step["duration_ms"] >= 0.0

    def test_get_step_sequence_with_error(self) -> None:
        """Test step sequence with error."""
        trace = create_trace_with_error()
        analyzer = TraceAnalyzer()

        steps = analyzer.get_step_sequence(trace)
        assert len(steps) == 1

        # Step with error should have error field
        error_step = steps[0]
        assert error_step.get("error") is not None

    def test_analyze_token_aggregation(self) -> None:
        """Test that tokens are aggregated correctly across multiple calls."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        # Should sum tokens from all model calls
        assert metrics.total_tokens == 450
        assert metrics.prompt_tokens == 300
        assert metrics.completion_tokens == 150

    def test_analyze_error_rate_calculation(self) -> None:
        """Test error rate calculation."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        # No errors, so error rate should be 0
        assert metrics.error_rate == 0.0

        # Trace with error
        error_trace = create_trace_with_error()
        error_metrics = analyzer.analyze(error_trace)
        assert error_metrics.errors > 0
        # Error rate should be between 0 and 1
        assert 0.0 <= error_metrics.error_rate <= 1.0

    def test_analyze_duration_calculation(self) -> None:
        """Test total duration calculation."""
        trace = create_test_trace()
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        # Duration should be positive
        assert metrics.total_duration_ms >= 0.0

        # For our test trace with events spaced 0.1s apart
        # Duration should be approximately (num_events - 1) * 100ms
        expected_min_duration = (len(trace.events) - 1) * 100.0
        assert metrics.total_duration_ms >= expected_min_duration * 0.9  # Allow some tolerance

    def test_query_empty_trace(self) -> None:
        """Test querying an empty trace."""
        trace = Trace(trace_id="empty", events=[], metadata={})
        analyzer = TraceAnalyzer()

        results = analyzer.query(trace, event_type="model_called")
        assert len(results) == 0

        results = analyzer.query(trace, filter_func=lambda e: True)
        assert len(results) == 0

    def test_search_empty_trace(self) -> None:
        """Test searching an empty trace."""
        trace = Trace(trace_id="empty", events=[], metadata={})
        analyzer = TraceAnalyzer()

        results = analyzer.search(trace, "anything")
        assert len(results) == 0

    def test_get_timeline_empty_trace(self) -> None:
        """Test getting timeline of empty trace."""
        trace = Trace(trace_id="empty", events=[], metadata={})
        analyzer = TraceAnalyzer()

        timeline = analyzer.get_timeline(trace)
        assert len(timeline) == 0

    def test_get_step_sequence_empty_trace(self) -> None:
        """Test getting step sequence of empty trace."""
        trace = Trace(trace_id="empty", events=[], metadata={})
        analyzer = TraceAnalyzer()

        steps = analyzer.get_step_sequence(trace)
        assert len(steps) == 0

    def test_search_in_list_values(self) -> None:
        """Test that search works in list values."""
        trace = Trace(trace_id="list_test", events=[], metadata={})
        trace.add_event(
            "test_event",
            {
                "items": ["apple", "banana", "cherry"],
                "other": "not_found",
            },
        )

        analyzer = TraceAnalyzer()
        results = analyzer.search(trace, "banana")
        assert len(results) == 1

        results = analyzer.search(trace, "not_in_list")
        assert len(results) == 0
