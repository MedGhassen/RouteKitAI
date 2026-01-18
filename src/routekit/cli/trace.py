"""CLI command for viewing traces."""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from routekit.observability.exporters.jsonl import JSONLExporter

if TYPE_CHECKING:
    import typer
    from rich.console import Console
    from rich.json import JSON
    from rich.table import Table
else:
    try:
        import typer
        from rich.console import Console
        from rich.json import JSON
        from rich.table import Table
    except ImportError as e:
        raise ImportError(
            "CLI dependencies not installed. Install with: pip install typer rich"
        ) from e

app = typer.Typer(name="trace", help="View and inspect agent execution traces")
console = Console()


def trace_command(
    trace_id: str = typer.Argument(..., help="Trace ID to view"),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-t", help="Directory containing trace files"
    ),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, raw"),
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


if __name__ == "__main__" and app is not None:
    app()
