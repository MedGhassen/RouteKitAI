"""CLI command for starting the trace visualization web server."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
else:
    try:
        import typer
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # type: ignore[import-not-found]
        from fastapi.middleware.cors import CORSMiddleware  # type: ignore[import-not-found]
        from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "Web UI dependencies not installed. Install with: pip install 'routekit[ui]'"
        ) from e

from routekit.observability.analyzer import TraceAnalyzer
from routekit.observability.exporters.jsonl import JSONLExporter
from routekit.observability.streaming import get_broadcaster

app = FastAPI(title="RouteKit Trace Viewer", version="0.1.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/traces")
async def list_traces() -> JSONResponse:
    """List all available traces with summary metrics.

    Returns:
        JSON response with list of traces and their metrics
    """
    trace_dir = os.environ.get("ROUTEKIT_TRACE_DIR", ".routekit/traces")
    trace_path = Path(trace_dir)
    if not trace_path.exists():
        return JSONResponse({"traces": []})

    traces = []
    exporter = JSONLExporter(output_dir=trace_path)
    analyzer = TraceAnalyzer()

    for trace_file in sorted(
        trace_path.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        trace_id = trace_file.stem
        try:
            trace = await exporter.load(trace_id)
            if trace:
                metrics = analyzer.analyze(trace)
                traces.append(
                    {
                        "trace_id": trace_id,
                        "total_events": metrics.total_events,
                        "duration_ms": metrics.total_duration_ms,
                        "model_calls": metrics.model_calls,
                        "tool_calls": metrics.tool_calls,
                        "errors": metrics.errors,
                        "total_tokens": metrics.total_tokens,
                        "error_rate": metrics.error_rate,
                    }
                )
        except Exception:
            # Skip corrupted traces
            continue

    return JSONResponse({"traces": traces})


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str) -> JSONResponse:
    """Get full trace data including metrics, timeline, and steps.

    Args:
        trace_id: Trace ID to retrieve

    Returns:
        JSON response with complete trace data
    """
    try:
        trace_dir = os.environ.get("ROUTEKIT_TRACE_DIR", ".routekit/traces")
        trace_path = Path(trace_dir)
        if not trace_path.exists():
            raise HTTPException(status_code=404, detail="Trace directory not found")

        exporter = JSONLExporter(output_dir=trace_path)
        trace = await exporter.load(trace_id)

        if not trace:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

        analyzer = TraceAnalyzer()
        metrics = analyzer.analyze(trace)
        timeline = analyzer.get_timeline(trace)
        steps = analyzer.get_step_sequence(trace)

        # Convert timeline entries to serializable format
        timeline_data = []
        for entry in timeline:
            try:
                event_obj = entry.get("event")
                if event_obj is None:
                    continue
                # Handle both TraceEvent objects and dicts
                if hasattr(event_obj, "model_dump"):
                    event_data = event_obj.model_dump(mode="json")
                else:
                    event_data = event_obj
                timeline_data.append(
                    {
                        "event": event_data,
                        "relative_time_ms": entry.get("relative_time_ms", 0.0),
                        "duration_ms": entry.get("duration_ms", 0.0),
                        "index": entry.get("index", 0),
                    }
                )
            except Exception:
                # Skip problematic entries
                continue

        return JSONResponse(
            {
                "trace": trace.model_dump(mode="json"),
                "metrics": metrics.model_dump(mode="json"),
                "timeline": timeline_data,
                "steps": steps,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading trace: {str(e)}") from e


@app.get("/api/traces/{trace_id}/events")
async def get_trace_events(
    trace_id: str,
    event_type: str | None = None,
) -> JSONResponse:
    """Get events from a trace, optionally filtered by type.

    Args:
        trace_id: Trace ID
        event_type: Optional event type filter

    Returns:
        JSON response with filtered events
    """
    trace_dir = os.environ.get("ROUTEKIT_TRACE_DIR", ".routekit/traces")
    trace_path = Path(trace_dir)
    exporter = JSONLExporter(output_dir=trace_path)
    trace = await exporter.load(trace_id)

    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    analyzer = TraceAnalyzer()
    events = analyzer.query(trace, event_type=event_type)

    return JSONResponse({"events": [e.model_dump() for e in events]})


@app.get("/api/traces/{trace_id}/search")
async def search_trace(
    trace_id: str,
    query: str,
) -> JSONResponse:
    """Search events in a trace.

    Args:
        trace_id: Trace ID
        query: Search query

    Returns:
        JSON response with matching events
    """
    trace_dir = os.environ.get("ROUTEKIT_TRACE_DIR", ".routekit/traces")
    trace_path = Path(trace_dir)
    exporter = JSONLExporter(output_dir=trace_path)
    trace = await exporter.load(trace_id)

    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    analyzer = TraceAnalyzer()
    results = analyzer.search(trace, query)

    return JSONResponse({"results": [e.model_dump() for e in results]})


@app.websocket("/ws/traces/{trace_id}")
async def websocket_trace_stream(websocket: WebSocket, trace_id: str) -> None:
    """WebSocket endpoint for real-time trace event streaming.

    Args:
        websocket: WebSocket connection
        trace_id: Trace ID to stream (use '*' for all traces)
    """
    await websocket.accept()
    broadcaster = get_broadcaster()
    queue = await broadcaster.subscribe()

    try:
        while True:
            try:
                # Get event from queue
                event = await queue.get()
                queue.task_done()

                # Filter by trace_id if not '*'
                if trace_id != "*" and event.data.get("trace_id") != trace_id:
                    continue

                # Send event as JSON
                await websocket.send_json(
                    {
                        "type": event.type,
                        "timestamp": event.timestamp,
                        "data": event.data,
                    }
                )
            except WebSocketDisconnect:
                break
            except Exception as e:
                await websocket.send_json({"error": str(e)})
                break
    finally:
        await broadcaster.unsubscribe(queue)


@app.get("/api/traces/{trace_id}/stream")
async def sse_trace_stream(trace_id: str) -> StreamingResponse:
    """Server-Sent Events (SSE) endpoint for real-time trace event streaming.

    Args:
        trace_id: Trace ID to stream (use '*' for all traces)

    Returns:
        StreamingResponse with SSE-formatted events
    """
    broadcaster = get_broadcaster()

    async def event_generator() -> AsyncIterator[str]:
        queue = await broadcaster.subscribe()
        try:
            async for event_data in broadcaster.stream_events(
                queue, trace_id if trace_id != "*" else None
            ):
                yield event_data
        finally:
            await broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
async def index() -> HTMLResponse:
    """Serve the trace visualization dashboard."""
    html_content = _get_dashboard_html()
    return HTMLResponse(html_content)


def _get_dashboard_html() -> str:
    """Get the HTML dashboard content."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RouteKit Trace Viewer</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        h1 {
            color: #2563eb;
            margin-bottom: 10px;
        }

        .trace-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }

        .trace-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .trace-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-color: #2563eb;
        }

        .trace-card.selected {
            border-color: #2563eb;
            background: #eff6ff;
        }

        .trace-card h3 {
            color: #1f2937;
            margin-bottom: 10px;
            font-size: 14px;
            font-weight: 600;
            word-break: break-all;
        }

        .trace-card .metrics {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            font-size: 12px;
        }

        .trace-card .metric {
            display: flex;
            justify-content: space-between;
        }

        .trace-card .metric-label {
            color: #6b7280;
        }

        .trace-card .metric-value {
            font-weight: 600;
            color: #1f2937;
        }

        .trace-detail {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: none;
        }

        .trace-detail.active {
            display: block;
        }

        .detail-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e5e7eb;
        }

        .detail-header h2 {
            color: #1f2937;
        }

        .close-btn {
            background: #ef4444;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }

        .close-btn:hover {
            background: #dc2626;
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }

        .metric-card {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 15px;
        }

        .metric-card h4 {
            color: #6b7280;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .metric-card .value {
            font-size: 24px;
            font-weight: 700;
            color: #1f2937;
        }

        .metric-card .unit {
            font-size: 14px;
            color: #6b7280;
            margin-left: 4px;
        }

        .chart-container {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .chart-container h3 {
            margin-bottom: 15px;
            color: #1f2937;
        }

        .timeline-container {
            margin-top: 20px;
        }

        .timeline-event {
            display: flex;
            align-items: center;
            padding: 10px;
            margin: 5px 0;
            background: #f9fafb;
            border-left: 4px solid #2563eb;
            border-radius: 4px;
            cursor: pointer;
        }

        .timeline-event:hover {
            background: #f3f4f6;
        }

        .timeline-event.error {
            border-left-color: #ef4444;
        }

        .timeline-event.model {
            border-left-color: #10b981;
        }

        .timeline-event.tool {
            border-left-color: #f59e0b;
        }

        .event-time {
            min-width: 100px;
            font-size: 12px;
            color: #6b7280;
        }

        .event-type {
            min-width: 150px;
            font-weight: 600;
            color: #1f2937;
        }

        .event-details {
            flex: 1;
            font-size: 12px;
            color: #6b7280;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #6b7280;
        }

        .error {
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #991b1b;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }

        .steps-container {
            margin-top: 20px;
        }

        .step-card {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .step-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .step-id {
            font-weight: 600;
            color: #1f2937;
        }

        .step-duration {
            font-size: 12px;
            color: #6b7280;
        }

        .step-error {
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #991b1b;
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 RouteKit Trace Viewer</h1>
            <p>Visualize and analyze agent execution traces</p>
        </header>

        <div id="trace-list" class="trace-list">
            <div class="loading">Loading traces...</div>
        </div>

        <div id="trace-detail" class="trace-detail">
            <div class="detail-header">
                <h2 id="detail-title">Trace Details</h2>
                <button class="close-btn" onclick="closeDetail()">Close</button>
            </div>

            <div id="detail-content">
                <div class="loading">Loading trace data...</div>
            </div>
        </div>
    </div>

    <script>
        let currentTraceId = null;
        let charts = {};

        // Load traces on page load
        async function loadTraces() {
            try {
                const response = await fetch('/api/traces');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const data = await response.json();
                renderTraceList(data.traces || []);
            } catch (error) {
                document.getElementById('trace-list').innerHTML =
                    '<div class="error">Error loading traces: ' + error.message + '</div>';
            }
        }

        function renderTraceList(traces) {
            const container = document.getElementById('trace-list');

            if (traces.length === 0) {
                container.innerHTML = '<div class="loading">No traces found</div>';
                return;
            }

            container.innerHTML = traces.map(trace => `
                <div class="trace-card" onclick="loadTrace('${trace.trace_id}')">
                    <h3>${trace.trace_id}</h3>
                    <div class="metrics">
                        <div class="metric">
                            <span class="metric-label">Events:</span>
                            <span class="metric-value">${trace.total_events}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Duration:</span>
                            <span class="metric-value">${trace.duration_ms.toFixed(0)}ms</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Model Calls:</span>
                            <span class="metric-value">${trace.model_calls}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Tool Calls:</span>
                            <span class="metric-value">${trace.tool_calls}</span>
                        </div>
                        ${trace.errors > 0 ? `
                        <div class="metric">
                            <span class="metric-label">Errors:</span>
                            <span class="metric-value" style="color: #ef4444;">${trace.errors}</span>
                        </div>
                        ` : ''}
                        ${trace.total_tokens > 0 ? `
                        <div class="metric">
                            <span class="metric-label">Tokens:</span>
                            <span class="metric-value">${trace.total_tokens}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `).join('');
        }

        async function loadTrace(traceId) {
            currentTraceId = traceId;

            // Update selected card
            document.querySelectorAll('.trace-card').forEach(card => {
                card.classList.remove('selected');
                if (card.querySelector('h3').textContent === traceId) {
                    card.classList.add('selected');
                }
            });

            // Show detail panel
            document.getElementById('trace-detail').classList.add('active');
            document.getElementById('detail-content').innerHTML = '<div class="loading">Loading...</div>';

            try {
                const response = await fetch(`/api/traces/${traceId}`);
                if (!response.ok) {
                    const errorText = await response.text();
                    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                    try {
                        const errorJson = JSON.parse(errorText);
                        errorMessage = errorJson.detail || errorMessage;
                    } catch {
                        // If not JSON, use the text as-is (might be HTML)
                        if (errorText.length < 200) {
                            errorMessage = errorText;
                        }
                    }
                    throw new Error(errorMessage);
                }
                const data = await response.json();
                renderTraceDetail(data);
            } catch (error) {
                document.getElementById('detail-content').innerHTML =
                    '<div class="error">Error loading trace: ' + error.message + '</div>';
            }
        }

        function renderTraceDetail(data) {
            const metrics = data.metrics;
            const timeline = data.timeline;
            const steps = data.steps;

            let html = `
                <div class="metrics-grid">
                    <div class="metric-card">
                        <h4>Total Events</h4>
                        <div class="value">${metrics.total_events}<span class="unit">events</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Duration</h4>
                        <div class="value">${metrics.total_duration_ms.toFixed(2)}<span class="unit">ms</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Model Calls</h4>
                        <div class="value">${metrics.model_calls}<span class="unit">calls</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Tool Calls</h4>
                        <div class="value">${metrics.tool_calls}<span class="unit">calls</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Errors</h4>
                        <div class="value" style="color: ${metrics.errors > 0 ? '#ef4444' : '#10b981'}">${metrics.errors}<span class="unit">errors</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Error Rate</h4>
                        <div class="value">${(metrics.error_rate * 100).toFixed(1)}<span class="unit">%</span></div>
                    </div>
                    ${metrics.total_tokens > 0 ? `
                    <div class="metric-card">
                        <h4>Total Tokens</h4>
                        <div class="value">${metrics.total_tokens}<span class="unit">tokens</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Prompt Tokens</h4>
                        <div class="value">${metrics.prompt_tokens}<span class="unit">tokens</span></div>
                    </div>
                    <div class="metric-card">
                        <h4>Completion Tokens</h4>
                        <div class="value">${metrics.completion_tokens}<span class="unit">tokens</span></div>
                    </div>
                    ` : ''}
                    ${metrics.avg_model_latency_ms > 0 ? `
                    <div class="metric-card">
                        <h4>Avg Model Latency</h4>
                        <div class="value">${metrics.avg_model_latency_ms.toFixed(2)}<span class="unit">ms</span></div>
                    </div>
                    ` : ''}
                    ${metrics.avg_tool_latency_ms > 0 ? `
                    <div class="metric-card">
                        <h4>Avg Tool Latency</h4>
                        <div class="value">${metrics.avg_tool_latency_ms.toFixed(2)}<span class="unit">ms</span></div>
                    </div>
                    ` : ''}
                </div>
            `;

            // Add charts
            if (metrics.total_tokens > 0) {
                html += `
                    <div class="chart-container">
                        <h3>Token Usage</h3>
                        <canvas id="tokenChart"></canvas>
                    </div>
                `;
            }

            if (timeline.length > 0) {
                html += `
                    <div class="chart-container">
                        <h3>Event Timeline</h3>
                        <canvas id="timelineChart"></canvas>
                    </div>
                `;
            }

            // Add timeline events
            html += `
                <div class="timeline-container">
                    <h3>Event Timeline</h3>
                    <div id="timeline-events"></div>
                </div>
            `;

            // Add steps
            if (steps.length > 0) {
                html += `
                    <div class="steps-container">
                        <h3>Execution Steps</h3>
                        ${steps.map(step => `
                            <div class="step-card">
                                <div class="step-header">
                                    <span class="step-id">${step.step_id}</span>
                                    <span class="step-duration">${step.duration_ms.toFixed(2)}ms</span>
                                </div>
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 10px;">
                                    Type: ${step.step_type} | Events: ${step.events.length}
                                </div>
                                ${step.error ? `
                                    <div class="step-error">Error: ${step.error}</div>
                                ` : ''}
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            document.getElementById('detail-content').innerHTML = html;

            // Render charts
            if (metrics.total_tokens > 0) {
                renderTokenChart(metrics);
            }

            if (timeline.length > 0) {
                renderTimelineChart(timeline);
                renderTimelineEvents(timeline);
            }
        }

        function renderTokenChart(metrics) {
            const ctx = document.getElementById('tokenChart');
            if (charts.tokenChart) {
                charts.tokenChart.destroy();
            }

            charts.tokenChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Prompt Tokens', 'Completion Tokens'],
                    datasets: [{
                        data: [metrics.prompt_tokens, metrics.completion_tokens],
                        backgroundColor: ['#3b82f6', '#10b981'],
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        }
                    }
                }
            });
        }

        function renderTimelineChart(timeline) {
            const ctx = document.getElementById('timelineChart');
            if (charts.timelineChart) {
                charts.timelineChart.destroy();
            }

            const eventTypes = {};
            timeline.forEach(entry => {
                const event = entry.event || {};
                const type = event.type || 'unknown';
                eventTypes[type] = (eventTypes[type] || 0) + 1;
            });

            charts.timelineChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: Object.keys(eventTypes),
                    datasets: [{
                        label: 'Event Count',
                        data: Object.values(eventTypes),
                        backgroundColor: '#3b82f6',
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            display: false,
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                        }
                    }
                }
            });
        }

        function renderTimelineEvents(timeline) {
            const container = document.getElementById('timeline-events');
            container.innerHTML = timeline.map(entry => {
                const event = entry.event || {};
                const eventType = event.type || 'unknown';
                const typeClass = eventType.includes('error') ? 'error' :
                                 eventType.includes('model') ? 'model' :
                                 eventType.includes('tool') ? 'tool' : '';

                const eventData = event.data || {};
                const details = JSON.stringify(eventData).substring(0, 100);
                const relativeTime = entry.relative_time_ms || 0;

                return `
                    <div class="timeline-event ${typeClass}" onclick="showEventDetails(${entry.index || 0})">
                        <div class="event-time">${relativeTime.toFixed(2)}ms</div>
                        <div class="event-type">${eventType}</div>
                        <div class="event-details">${details}${JSON.stringify(eventData).length > 100 ? '...' : ''}</div>
                    </div>
                `;
            }).join('');
        }

        function showEventDetails(index) {
            // Could show modal with full event details
            alert('Event details at index ' + index);
        }

        function closeDetail() {
            document.getElementById('trace-detail').classList.remove('active');
            currentTraceId = null;

            // Destroy charts
            Object.values(charts).forEach(chart => chart.destroy());
            charts = {};
        }

        // Load traces on page load
        loadTraces();

        // Auto-refresh every 5 seconds
        setInterval(loadTraces, 5000);
    </script>
</body>
</html>
    """


def serve_command(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run server on"),
    trace_dir: str = typer.Option(
        ".routekit/traces", "--trace-dir", "-t", help="Directory containing trace files"
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
) -> None:
    """Start the trace visualization web server.

    Examples:
        routekit serve
        routekit serve --port 3000
        routekit serve --host 0.0.0.0 --port 8080
    """
    import uvicorn

    # Set trace directory as environment variable for API endpoints
    os.environ["ROUTEKIT_TRACE_DIR"] = trace_dir

    try:
        from rich.console import Console

        console = Console()
        console.print("\n[bold green]🚀 Starting RouteKit Trace Viewer[/bold green]")
        console.print(f"[dim]Server running at http://{host}:{port}[/dim]")
        console.print(f"[dim]Trace directory: {trace_dir}[/dim]\n")
    except ImportError:
        print("\n🚀 Starting RouteKit Trace Viewer")
        print(f"Server running at http://{host}:{port}")
        print(f"Trace directory: {trace_dir}\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__" and app is not None:
    serve_command()
