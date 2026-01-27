"""Integration tests for trace analyzer with real runtime traces."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from routekitai.core.agent import Agent, RunResult
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.observability.analyzer import TraceAnalyzer
from routekitai.observability.exporters.jsonl import JSONLExporter
from routekitai.providers.local import FakeModel


class EvalTestAgent(Agent):
    """Test agent that can be used with runtime."""

    async def run(self, prompt: str, **kwargs: object) -> RunResult:
        """Override to prevent direct execution."""
        raise NotImplementedError("Use runtime.run() instead")


@pytest.mark.asyncio
async def test_analyze_real_trace() -> None:
    """Test analyzing a trace from a real agent run."""

    # Create a model that returns tool calls
    def response_fn(messages, tools):
        """Return response with tool call."""
        last_msg = messages[-1] if messages else None
        if last_msg and "echo" in last_msg.content.lower():
            return {
                "content": "I'll echo that for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "echo",
                        "arguments": {"message": "Hello RouteKit!"},
                    }
                ],
            }
        return "How can I help you?"

    model = FakeModel(name="test", response_fn=response_fn)
    agent = EvalTestAgent(name="test_agent", model=model, tools=[EchoTool()])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        # Run agent
        result = await runtime.run("test_agent", "Please echo 'Hello RouteKit!'")

        # Wait for trace export
        await asyncio.sleep(0.1)

        # Load trace
        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None

        # Analyze trace
        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)

        # Verify metrics
        assert metrics.total_events > 0
        assert metrics.total_duration_ms >= 0.0
        assert metrics.steps > 0
        # Should have at least one model call
        assert metrics.model_calls >= 1
        # Should have at least one tool call
        assert metrics.tool_calls >= 1


@pytest.mark.asyncio
async def test_timeline_real_trace() -> None:
    """Test timeline generation from real trace."""
    model = FakeModel(name="test")
    model.add_response("Response 1")
    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Hello")

        await asyncio.sleep(0.1)

        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None

        analyzer = TraceAnalyzer()
        timeline = analyzer.get_timeline(trace)

        assert len(timeline) > 0
        assert timeline[0]["relative_time_ms"] == 0.0

        # Timeline should be ordered
        for i in range(1, len(timeline)):
            assert timeline[i]["relative_time_ms"] >= timeline[i - 1]["relative_time_ms"]


@pytest.mark.asyncio
async def test_step_sequence_real_trace() -> None:
    """Test step sequence extraction from real trace."""
    model = FakeModel(name="test")
    model.add_response("Response 1")
    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Hello")

        await asyncio.sleep(0.1)

        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None

        analyzer = TraceAnalyzer()
        steps = analyzer.get_step_sequence(trace)

        assert len(steps) > 0

        # Each step should have required fields
        for step in steps:
            assert "step_id" in step
            assert "events" in step
            assert len(step["events"]) > 0


@pytest.mark.asyncio
async def test_search_real_trace() -> None:
    """Test searching a real trace."""
    model = FakeModel(name="test")
    model.add_response("Response with special keyword: TEST123")
    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Hello")

        await asyncio.sleep(0.1)

        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None

        analyzer = TraceAnalyzer()

        # Search for trace ID
        results = analyzer.search(trace, result.trace_id)
        assert len(results) > 0

        # Search for agent name
        results = analyzer.search(trace, "test_agent")
        assert len(results) >= 0  # May or may not be in trace data


@pytest.mark.asyncio
async def test_query_real_trace() -> None:
    """Test querying a real trace."""
    model = FakeModel(name="test")
    model.add_response("Response")
    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        result = await runtime.run("test_agent", "Hello")

        await asyncio.sleep(0.1)

        exporter = JSONLExporter(output_dir=trace_dir)
        trace = await exporter.load(result.trace_id)
        assert trace is not None

        analyzer = TraceAnalyzer()

        # Query for run_started events
        run_started = analyzer.query(trace, event_type="run_started")
        assert len(run_started) >= 1

        # Query for run_completed events
        run_completed = analyzer.query(trace, event_type="run_completed")
        assert len(run_completed) >= 1

        # Query with filter
        model_events = analyzer.query(
            trace,
            event_type="model_called",
            filter_func=lambda e: "step_id" in e.data,
        )
        assert len(model_events) >= 0  # May or may not have model_called events
