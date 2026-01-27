"""CLI command for searching traces."""

import asyncio
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: pip install typer rich") from e

from routekitai.observability.analyzer import TraceAnalyzer
from routekitai.observability.exporters.jsonl import JSONLExporter

app = typer.Typer(name="trace-search", help="Search traces by content")
console = Console()


def search_command(
    query: str = typer.Argument(..., help="Search query"),
    trace_id: str | None = typer.Option(
        None, "--trace-id", "-t", help="Specific trace ID to search (optional)"
    ),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-d", help="Directory containing trace files"
    ),
    event_type: str | None = typer.Option(None, "--event-type", "-e", help="Filter by event type"),
) -> None:
    """Search traces by content.

    Examples:
        routekit trace-search "error"
        routekit trace-search "model" --trace-id abc123
        routekit trace-search "tool" --event-type tool_called
    """
    # Determine trace directory
    trace_path: Path
    if trace_dir is None:
        trace_path = Path(".routekit") / "traces"
    else:
        trace_path = Path(trace_dir)

    if not trace_path.exists():
        console.print(f"[red]Error: Trace directory not found: {trace_path}[/red]")
        raise typer.Exit(1)

    exporter = JSONLExporter(output_dir=trace_path)
    analyzer = TraceAnalyzer()

    # Search in specific trace or all traces
    if trace_id:
        trace = asyncio.run(exporter.load(trace_id))
        if trace is None:
            console.print(f"[red]Error: Trace '{trace_id}' not found[/red]")
            raise typer.Exit(1)

        results = analyzer.search(trace, query)
        if event_type:
            results = [r for r in results if r.type == event_type]

        _display_search_results(trace_id, results)
    else:
        # Search all traces
        trace_files = list(trace_path.glob("*.jsonl"))
        if not trace_files:
            console.print(f"[yellow]No traces found in {trace_path}[/yellow]")
            raise typer.Exit(0)

        all_results: list[tuple[str, list]] = []
        for trace_file in trace_files:
            trace_id_from_file = trace_file.stem
            trace = asyncio.run(exporter.load(trace_id_from_file))
            if trace:
                results = analyzer.search(trace, query)
                if event_type:
                    results = [r for r in results if r.type == event_type]
                if results:
                    all_results.append((trace_id_from_file, results))

        if not all_results:
            console.print(f"[yellow]No matches found for query: '{query}'[/yellow]")
            raise typer.Exit(0)

        console.print(f"\n[bold]Search Results for '{query}':[/bold]\n")
        for tid, results in all_results:
            console.print(f"[cyan]Trace: {tid}[/cyan] ({len(results)} matches)")
            _display_search_results(tid, results, show_trace_id=False)
            console.print()


def _display_search_results(trace_id: str, results: list, show_trace_id: bool = True) -> None:
    """Display search results in a table.

    Args:
        trace_id: Trace ID
        results: List of matching events
        show_trace_id: Whether to show trace ID in table
    """
    if not results:
        console.print("[yellow]No matches found[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    if show_trace_id:
        table.add_column("Trace ID", style="cyan")
    table.add_column("Event Type", style="yellow")
    table.add_column("Timestamp", style="green")
    table.add_column("Preview", style="white")

    for event in results[:50]:  # Limit to 50 results
        preview = str(event.data)[:100]
        if len(str(event.data)) > 100:
            preview += "..."
        row = [event.type, f"{event.timestamp:.3f}", preview]
        if show_trace_id:
            row.insert(0, trace_id)
        table.add_row(*row)

    console.print(table)
    if len(results) > 50:
        console.print(f"[dim]... and {len(results) - 50} more results[/dim]")


if __name__ == "__main__" and app is not None:
    app()
