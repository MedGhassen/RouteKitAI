"""Tests for OTEL exporter."""

import pytest

from routekit.observability.exporters.otel import OTELExporter
from routekit.observability.trace import Trace


@pytest.mark.asyncio
async def test_otel_exporter_no_endpoint() -> None:
    """Test OTEL exporter without endpoint (debug mode)."""
    exporter = OTELExporter()

    trace = Trace(trace_id="test-trace")
    trace.add_event("test_event", {"key": "value"})

    # Should not raise (just logs)
    await exporter.export(trace)


@pytest.mark.asyncio
async def test_otel_exporter_conversion() -> None:
    """Test trace to OTEL conversion."""
    exporter = OTELExporter()

    trace = Trace(trace_id="test-trace")
    trace.add_event("step_started", {"step_id": "step1"})
    trace.add_event("step_completed", {"step_id": "step1"})

    otel_data = exporter._convert_trace_to_otel(trace)

    assert "resourceSpans" in otel_data
    assert len(otel_data["resourceSpans"]) > 0
    spans = otel_data["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
