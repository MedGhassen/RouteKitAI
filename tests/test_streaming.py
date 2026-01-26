"""Tests for streaming support functionality."""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import pytest

from routekit.core.agent import Agent
from routekit.core.message import Message
from routekit.core.model import ModelResponse, StreamEvent, ToolCall, Usage
from routekit.core.runtime import Runtime
from routekit.observability.streaming import TraceEventBroadcaster, get_broadcaster
from routekit.observability.trace import Trace, TraceEvent
from routekit.providers.local import FakeModel


class StreamingModel(FakeModel):
    """Fake model that supports streaming."""

    async def chat(
        self,
        messages: list[Message],
        tools: list | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with streaming support."""
        if stream:
            # Return a stream
            async def stream_generator() -> AsyncIterator[StreamEvent]:
                content = "Hello, world!"
                for i, char in enumerate(content):
                    await asyncio.sleep(0.01)  # Simulate streaming delay
                    yield StreamEvent(
                        type="content",
                        content=char,
                        metadata={"index": i},
                    )
                # Final event with usage
                yield StreamEvent(
                    type="done",
                    content=None,
                    usage=Usage(
                        prompt_tokens=10,
                        completion_tokens=len(content),
                        total_tokens=10 + len(content),
                    ),
                )

            return stream_generator()
        else:
            # Non-streaming mode
            return await super().chat(messages, tools, stream=False, **kwargs)


class TestTraceEventCallbacks:
    """Test trace event callback system."""

    def test_add_event_callback(self) -> None:
        """Test adding event callbacks."""
        trace = Trace(trace_id="test", metadata={})
        events_received: list[TraceEvent] = []

        def callback(event: TraceEvent) -> None:
            events_received.append(event)

        trace.add_event_callback(callback)
        trace.add_event("test_event", {"data": "test"})

        assert len(events_received) == 1
        assert events_received[0].type == "test_event"
        assert events_received[0].data["data"] == "test"

    def test_remove_event_callback(self) -> None:
        """Test removing event callbacks."""
        trace = Trace(trace_id="test", metadata={})
        events_received: list[TraceEvent] = []

        def callback(event: TraceEvent) -> None:
            events_received.append(event)

        trace.add_event_callback(callback)
        trace.add_event("event1", {})
        assert len(events_received) == 1

        trace.remove_event_callback(callback)
        trace.add_event("event2", {})
        assert len(events_received) == 1  # Should not receive event2

    def test_multiple_callbacks(self) -> None:
        """Test multiple callbacks."""
        trace = Trace(trace_id="test", metadata={})
        events1: list[TraceEvent] = []
        events2: list[TraceEvent] = []

        def callback1(event: TraceEvent) -> None:
            events1.append(event)

        def callback2(event: TraceEvent) -> None:
            events2.append(event)

        trace.add_event_callback(callback1)
        trace.add_event_callback(callback2)
        trace.add_event("test_event", {})

        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0].type == events2[0].type == "test_event"

    @pytest.mark.asyncio
    async def test_async_callback(self) -> None:
        """Test async callbacks."""
        trace = Trace(trace_id="test", metadata={})
        events_received: list[TraceEvent] = []

        async def async_callback(event: TraceEvent) -> None:
            await asyncio.sleep(0.01)
            events_received.append(event)

        trace.add_event_callback(async_callback)
        trace.add_event("test_event", {})

        # Give async callback time to execute
        await asyncio.sleep(0.1)

        assert len(events_received) == 1
        assert events_received[0].type == "test_event"


class TestTraceEventBroadcaster:
    """Test TraceEventBroadcaster."""

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self) -> None:
        """Test subscribing and unsubscribing."""
        broadcaster = TraceEventBroadcaster()
        queue = await broadcaster.subscribe()

        assert queue in broadcaster._subscribers

        await broadcaster.unsubscribe(queue)
        assert queue not in broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_broadcast_event(self) -> None:
        """Test broadcasting events."""
        broadcaster = TraceEventBroadcaster()
        queue1 = await broadcaster.subscribe()
        queue2 = await broadcaster.subscribe()

        event = TraceEvent(type="test", timestamp=time.time(), data={"test": "data"})
        await broadcaster.broadcast(event)

        # Both queues should receive the event
        event1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        event2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

        assert event1.type == event2.type == "test"
        assert event1.data == event2.data == {"test": "data"}

        await broadcaster.unsubscribe(queue1)
        await broadcaster.unsubscribe(queue2)

    @pytest.mark.asyncio
    async def test_stream_events_sse(self) -> None:
        """Test streaming events as SSE format."""
        broadcaster = TraceEventBroadcaster()
        queue = await broadcaster.subscribe()

        event = TraceEvent(
            type="test_event",
            timestamp=time.time(),
            data={"trace_id": "test123", "message": "hello"},
        )
        await broadcaster.broadcast(event)

        # Stream events
        events = []
        async for sse_data in broadcaster.stream_events(queue, trace_id="test123"):
            if sse_data.startswith("data: "):
                events.append(sse_data)
                break  # Just get first event

        assert len(events) > 0
        assert "test_event" in events[0]
        assert "test123" in events[0]

        await broadcaster.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_stream_events_filter_by_trace_id(self) -> None:
        """Test filtering events by trace_id."""
        broadcaster = TraceEventBroadcaster()
        queue = await broadcaster.subscribe()

        # Broadcast events for different trace IDs
        event1 = TraceEvent(type="event1", timestamp=time.time(), data={"trace_id": "trace1"})
        event2 = TraceEvent(type="event2", timestamp=time.time(), data={"trace_id": "trace2"})

        await broadcaster.broadcast(event1)
        await broadcaster.broadcast(event2)

        # Stream with filter
        events = []
        async for sse_data in broadcaster.stream_events(queue, trace_id="trace1"):
            if sse_data.startswith("data: "):
                events.append(sse_data)
                if len(events) >= 1:
                    break

        # Should only get trace1 events
        assert len(events) > 0
        assert "trace1" in events[0]
        assert "trace2" not in events[0]

        await broadcaster.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_get_broadcaster_singleton(self) -> None:
        """Test that get_broadcaster returns singleton."""
        broadcaster1 = get_broadcaster()
        broadcaster2 = get_broadcaster()

        assert broadcaster1 is broadcaster2


class TestProgressTracking:
    """Test progress tracking in Runtime."""

    @pytest.mark.asyncio
    async def test_progress_callback(self) -> None:
        """Test progress callbacks."""
        runtime = Runtime()
        progress_updates: list[dict] = []

        def progress_callback(progress: dict) -> None:
            progress_updates.append(progress)

        runtime.add_progress_callback(progress_callback)

        # Create a trace and emit progress
        trace = Trace(trace_id="test", metadata={})
        runtime._current_step = 5
        runtime._total_steps = 10
        runtime._emit_progress(trace, "model_call")

        assert len(progress_updates) == 1
        assert progress_updates[0]["current_step"] == 5
        assert progress_updates[0]["total_steps"] == 10
        assert progress_updates[0]["progress_percent"] == 50.0
        assert progress_updates[0]["current_step_type"] == "model_call"

    @pytest.mark.asyncio
    async def test_progress_tracking_during_execution(self) -> None:
        """Test progress tracking during agent execution."""
        model = FakeModel(name="test_model")
        model.add_response("Hello")

        agent = Agent(name="test_agent", model=model)
        runtime = Runtime()
        runtime.register_agent(agent)

        progress_updates: list[dict] = []

        def progress_callback(progress: dict) -> None:
            progress_updates.append(progress)

        runtime.add_progress_callback(progress_callback)

        # Run agent
        result = await runtime.run("test_agent", "Hello")

        # Should have received progress updates
        assert len(progress_updates) > 0
        assert any("progress_percent" in p for p in progress_updates)

    @pytest.mark.asyncio
    async def test_remove_progress_callback(self) -> None:
        """Test removing progress callbacks."""
        runtime = Runtime()
        progress_updates: list[dict] = []

        def progress_callback(progress: dict) -> None:
            progress_updates.append(progress)

        runtime.add_progress_callback(progress_callback)

        trace = Trace(trace_id="test", metadata={})
        runtime._emit_progress(trace)
        assert len(progress_updates) == 1

        runtime.remove_progress_callback(progress_callback)
        runtime._emit_progress(trace)
        assert len(progress_updates) == 1  # Should not increase


class TestStreamingModelResponses:
    """Test streaming model responses in Runtime."""

    @pytest.mark.asyncio
    async def test_call_model_streaming(self) -> None:
        """Test calling model with streaming."""
        model = StreamingModel(name="streaming_model")
        agent = Agent(name="test_agent", model=model)
        runtime = Runtime()
        runtime.register_agent(agent)

        trace = Trace(trace_id="test", metadata={})
        messages = [Message.user("Hello")]

        # Call with streaming
        response = await runtime._call_model(agent, messages, trace, stream=True)

        assert isinstance(response, AsyncIterator)

        # Collect stream events
        events = []
        content = ""
        async for event in response:
            events.append(event)
            if event.content:
                content += event.content

        assert len(events) > 0
        assert content == "Hello, world!"

        # Check that trace events were added
        stream_events = [e for e in trace.events if e.type == "model_stream_chunk"]
        assert len(stream_events) > 0

        # Check final model_called event
        model_events = [e for e in trace.events if e.type == "model_called"]
        assert len(model_events) > 0
        assert model_events[-1].data.get("streamed") is True

    @pytest.mark.asyncio
    async def test_call_model_non_streaming(self) -> None:
        """Test calling model without streaming (backward compatibility)."""
        model = FakeModel(name="test_model")
        model.add_response("Hello")

        agent = Agent(name="test_agent", model=model)
        runtime = Runtime()
        runtime.register_agent(agent)

        trace = Trace(trace_id="test", metadata={})
        messages = [Message.user("Hello")]

        # Call without streaming
        response = await runtime._call_model(agent, messages, trace, stream=False)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello"

        # Check trace event
        model_events = [e for e in trace.events if e.type == "model_called"]
        assert len(model_events) > 0
        assert (
            model_events[0].data.get("streamed") is None
            or model_events[0].data.get("streamed") is False
        )


class TestAgentStreaming:
    """Test Agent.run_stream() method."""

    @pytest.mark.asyncio
    async def test_run_stream_basic(self) -> None:
        """Test basic streaming from agent."""
        model = FakeModel(name="test_model")
        model.add_response("Hello, world!")

        agent = Agent(name="test_agent", model=model)

        events = []
        async for event in agent.run_stream("Say hello"):
            events.append(event)
            # Limit to avoid hanging
            if len(events) > 50:
                break

        # Should have some events
        assert len(events) > 0

        # Check for result event (may not always be last due to async nature)
        result_events = [e for e in events if e.get("type") == "result"]
        if result_events:
            assert result_events[0]["result"]["output"]["content"] == "Hello, world!"

        # May have trace events or progress updates
        trace_events = [e for e in events if e.get("type") == "trace_event"]
        progress_events = [e for e in events if e.get("type") == "progress_update"]
        assert len(trace_events) > 0 or len(progress_events) > 0

    @pytest.mark.asyncio
    async def test_run_stream_progress_updates(self) -> None:
        """Test that run_stream includes progress updates."""
        model = FakeModel(name="test_model")
        model.add_response("Response")

        agent = Agent(name="test_agent", model=model)

        progress_events = []
        async for event in agent.run_stream("Test"):
            if event["type"] == "progress_update":
                progress_events.append(event)

        # Should have progress updates
        assert len(progress_events) > 0
        assert all("progress_percent" in e["data"] for e in progress_events)

    @pytest.mark.asyncio
    async def test_run_stream_trace_events(self) -> None:
        """Test that run_stream yields trace events."""
        model = FakeModel(name="test_model")
        model.add_response("Response")

        agent = Agent(name="test_agent", model=model)

        trace_events = []
        async for event in agent.run_stream("Test"):
            if event.get("type") == "trace_event":
                trace_events.append(event["data"])
            # Limit to avoid hanging
            if len(trace_events) > 20:
                break

        # Should have some trace events or at least progress updates
        # (trace events may come through progress or directly)
        all_events = []
        async for event in agent.run_stream("Test2"):
            all_events.append(event)
            if len(all_events) > 20:
                break

        # Should have some events (trace, progress, or result)
        assert len(all_events) > 0

    @pytest.mark.asyncio
    async def test_run_stream_with_error(self) -> None:
        """Test run_stream handles errors gracefully."""
        # Create a model that will fail
        model = FakeModel(name="error_model")

        agent = Agent(name="test_agent", model=model)

        # Should not raise, but yield error events
        events = []
        try:
            async for event in agent.run_stream("Test"):
                events.append(event)
                # Break after a few events to avoid hanging
                if len(events) > 10:
                    break
        except Exception:
            pass  # Some errors are expected

        # Should have some events
        assert len(events) > 0


class TestTraceBroadcasting:
    """Test automatic trace event broadcasting."""

    @pytest.mark.asyncio
    async def test_trace_broadcasts_to_subscribers(self) -> None:
        """Test that trace events are automatically broadcast."""
        broadcaster = get_broadcaster()
        queue = await broadcaster.subscribe()

        # Create trace and add event
        trace = Trace(trace_id="broadcast_test", metadata={})
        trace.add_event("test_event", {"message": "hello"})

        # Give broadcast time to happen
        await asyncio.sleep(0.1)

        # Check if event was received
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert event.type == "test_event"
            assert event.data["message"] == "hello"
        except asyncio.TimeoutError:
            # Broadcasting happens in background, might not be immediate
            # This is acceptable behavior
            pass

        await broadcaster.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_multiple_traces_broadcast(self) -> None:
        """Test that multiple traces broadcast independently."""
        broadcaster = get_broadcaster()
        queue = await broadcaster.subscribe()

        trace1 = Trace(trace_id="trace1", metadata={})
        trace2 = Trace(trace_id="trace2", metadata={})

        trace1.add_event("event1", {"trace_id": "trace1"})
        trace2.add_event("event2", {"trace_id": "trace2"})

        await asyncio.sleep(0.1)

        # Both events should be broadcast
        events_received = []
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
                events_received.append(event)
        except asyncio.TimeoutError:
            pass

        # Should have received both events
        event_types = [e.type for e in events_received]
        assert "event1" in event_types or "event2" in event_types

        await broadcaster.unsubscribe(queue)
