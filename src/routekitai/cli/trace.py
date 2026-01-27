"""CLI command for viewing traces."""

import asyncio
import json
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.json import JSON
    from rich.table import Table
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: pip install typer rich") from e

from routekitai.observability.analyzer import TraceAnalyzer
from routekitai.observability.exporters.jsonl import JSONLExporter
from routekitai.observability.trace import Trace

app = typer.Typer(name="trace", help="View and inspect agent execution traces")
console = Console()


def trace_command(
    trace_id: str = typer.Argument(..., help="Trace ID to view"),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-t", help="Directory containing trace files"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, raw, timeline, steps"
    ),
) -> None:
    """View an agent execution trace.

    Examples:
        routekit trace abc123
        routekit trace abc123 --format json
        routekit trace abc123 --trace-dir ./custom_traces
    """
    # Determine trace directory
    trace_path: Path
    if trace_dir is None:
        trace_path = Path(".routekit") / "traces"
    else:
        trace_path = Path(trace_dir)

    if not trace_path.exists():
        console.print(f"[red]Error: Trace directory not found: {trace_dir}[/red]")
        raise typer.Exit(1)

    # Load trace
    exporter = JSONLExporter(output_dir=trace_path)
    trace = asyncio.run(exporter.load(trace_id))

    if trace is None:
        console.print(f"[red]Error: Trace '{trace_id}' not found in {trace_path}[/red]")
        raise typer.Exit(1)

    analyzer = TraceAnalyzer()

    if format == "json":
        # Output as JSON
        trace_data = {
            "trace_id": trace.trace_id,
            "metadata": trace.metadata,
            "events": [event.model_dump() for event in trace.events],
        }
        console.print(JSON(json.dumps(trace_data, indent=2)))
    elif format == "raw":
        # Raw JSONL output
        trace_file = trace_path / f"{trace_id}.jsonl"
        if trace_file.exists():
            console.print(trace_file.read_text())
        else:
            console.print(f"[red]Error: Trace file not found: {trace_file}[/red]")
    elif format == "timeline":
        # Timeline visualization
        _display_timeline(trace, analyzer)
    elif format == "steps":
        # Step-by-step execution view
        _display_steps(trace, analyzer)
    else:
        # Table format (default)
        console.print(f"\n[bold]Trace: {trace.trace_id}[/bold]")
        if trace.metadata:
            console.print(f"[dim]Metadata: {json.dumps(trace.metadata, indent=2)}[/dim]\n")

        table = Table(title="Trace Events", show_header=True, header_style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Timestamp", style="green")
        table.add_column("Data", style="yellow")

        for event in trace.events:
            data_str = json.dumps(event.data, indent=2) if event.data else ""
            # Truncate long data
            if len(data_str) > 200:
                data_str = data_str[:200] + "..."
            table.add_row(event.type, f"{event.timestamp:.3f}", data_str)

        console.print(table)
        console.print(f"\n[dim]Total events: {len(trace.events)}[/dim]")

        # Show quick metrics
        metrics = analyzer.analyze(trace)
        console.print(
            f"\n[dim]Duration: {metrics.total_duration_ms:.2f} ms | "
            f"Model calls: {metrics.model_calls} | "
            f"Tool calls: {metrics.tool_calls} | "
            f"Errors: {metrics.errors}[/dim]"
        )


def _display_timeline(trace: Trace, analyzer: TraceAnalyzer) -> None:
    """Display trace as a timeline.

    Args:
        trace: Trace to display
        analyzer: Trace analyzer instance
    """
    console.print(f"\n[bold cyan]Timeline: {trace.trace_id}[/bold cyan]\n")

    timeline = analyzer.get_timeline(trace)
    if not timeline:
        console.print("[yellow]No events in trace[/yellow]")
        return

    # Create timeline visualization
    max_time = max(entry["relative_time_ms"] for entry in timeline) if timeline else 0
    bar_width = 60

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Time (ms)", style="green", width=12)
    table.add_column("Event Type", style="cyan", width=20)
    table.add_column("Duration (ms)", style="yellow", width=15)
    table.add_column("Timeline", style="white", width=bar_width)
    table.add_column("Details", style="white")

    for entry in timeline:
        event = entry["event"]
        time_ms = entry["relative_time_ms"]
        duration_ms = entry["duration_ms"]

        # Create visual bar
        if max_time > 0:
            bar_pos = int((time_ms / max_time) * bar_width)
            bar = " " * bar_pos + "█"
        else:
            bar = "█"

        duration_str = f"{duration_ms:.2f}" if duration_ms > 0 else "-"
        details = json.dumps(event.data, indent=2)[:100]
        if len(json.dumps(event.data)) > 100:
            details += "..."

        table.add_row(
            f"{time_ms:.2f}",
            event.type,
            duration_str,
            bar,
            details,
        )

    console.print(table)


def _display_steps(trace: Trace, analyzer: TraceAnalyzer) -> None:
    """Display step-by-step execution view.

    Args:
        trace: Trace to display
        analyzer: Trace analyzer instance
    """
    console.print(f"\n[bold cyan]Step-by-Step Execution: {trace.trace_id}[/bold cyan]\n")

    steps = analyzer.get_step_sequence(trace)
    if not steps:
        console.print("[yellow]No steps found in trace[/yellow]")
        return

    for i, step in enumerate(steps, 1):
        step_id = step["step_id"]
        step_type = step["step_type"]
        duration_ms = step["duration_ms"]
        error = step.get("error")

        # Step header
        status = "[red]✗ ERROR[/red]" if error else "[green]✓ OK[/green]"
        console.print(f"\n[bold]Step {i}: {step_id}[/bold] ({step_type}) {status}")
        console.print(f"[dim]Duration: {duration_ms:.2f} ms[/dim]")

        if error:
            console.print(f"[red]Error: {error}[/red]")

        # Step events
        if step["events"]:
            event_table = Table(show_header=True, header_style="bold")
            event_table.add_column("Event", style="cyan", width=20)
            event_table.add_column("Data", style="white")

            for event in step["events"]:
                data_str = json.dumps(event.data, indent=2)[:200]
                if len(json.dumps(event.data)) > 200:
                    data_str += "..."
                event_table.add_row(event.type, data_str)

            console.print(event_table)


if __name__ == "__main__" and app is not None:
    app()
