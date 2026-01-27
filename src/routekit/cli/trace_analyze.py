"""CLI command for trace analysis and metrics."""

import asyncio
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError as e:
    raise ImportError(
        "CLI dependencies not installed. Install with: pip install typer rich"
    ) from e

from routekit.observability.analyzer import TraceAnalyzer
from routekit.observability.exporters.jsonl import JSONLExporter

app = typer.Typer(name="trace-analyze", help="Analyze trace metrics and performance")
console = Console()


def analyze_command(
    trace_id: str = typer.Argument(..., help="Trace ID to analyze"),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-t", help="Directory containing trace files"
    ),
) -> None:
    """Analyze a trace and display metrics.

    Examples:
        routekit trace-analyze abc123
        routekit trace-analyze abc123 --trace-dir ./custom_traces
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

    # Load trace
    exporter = JSONLExporter(output_dir=trace_path)
    trace = asyncio.run(exporter.load(trace_id))

    if trace is None:
        console.print(f"[red]Error: Trace '{trace_id}' not found in {trace_path}[/red]")
        raise typer.Exit(1)

    # Analyze trace
    analyzer = TraceAnalyzer()
    metrics = analyzer.analyze(trace)

    # Display metrics
    console.print(f"\n[bold cyan]Trace Analysis: {trace_id}[/bold cyan]\n")

    # Overview table
    overview_table = Table(title="Overview", show_header=True, header_style="bold magenta")
    overview_table.add_column("Metric", style="cyan")
    overview_table.add_column("Value", style="green")

    overview_table.add_row("Total Events", str(metrics.total_events))
    overview_table.add_row("Total Duration", f"{metrics.total_duration_ms:.2f} ms")
    overview_table.add_row("Steps", str(metrics.steps))
    overview_table.add_row("Errors", str(metrics.errors))
    overview_table.add_row("Error Rate", f"{metrics.error_rate * 100:.2f}%")

    console.print(overview_table)

    # Model calls table
    model_table = Table(title="Model Calls", show_header=True, header_style="bold magenta")
    model_table.add_column("Metric", style="cyan")
    model_table.add_column("Value", style="green")

    model_table.add_row("Total Calls", str(metrics.model_calls))
    model_table.add_row("Avg Latency", f"{metrics.avg_model_latency_ms:.2f} ms")
    model_table.add_row("Total Tokens", str(metrics.total_tokens))
    model_table.add_row("Prompt Tokens", str(metrics.prompt_tokens))
    model_table.add_row("Completion Tokens", str(metrics.completion_tokens))

    console.print("\n")
    console.print(model_table)

    # Tool calls table
    tool_table = Table(title="Tool Calls", show_header=True, header_style="bold magenta")
    tool_table.add_column("Metric", style="cyan")
    tool_table.add_column("Value", style="green")

    tool_table.add_row("Total Calls", str(metrics.tool_calls))
    tool_table.add_row("Avg Latency", f"{metrics.avg_tool_latency_ms:.2f} ms")

    console.print("\n")
    console.print(tool_table)

    # Cost estimation (if tokens available)
    if metrics.total_tokens > 0:
        console.print("\n[bold yellow]Cost Estimation (approximate):[/bold yellow]")
        cost_table = Table(show_header=True, header_style="bold magenta")
        cost_table.add_column("Provider", style="cyan")
        cost_table.add_column("Model", style="yellow")
        cost_table.add_column("Estimated Cost", style="green")

        # OpenAI GPT-4 pricing (example)
        gpt4_prompt_cost = (metrics.prompt_tokens / 1000) * 0.03
        gpt4_completion_cost = (metrics.completion_tokens / 1000) * 0.06
        cost_table.add_row("OpenAI", "gpt-4", f"${gpt4_prompt_cost + gpt4_completion_cost:.4f}")

        # OpenAI GPT-3.5 pricing
        gpt35_prompt_cost = (metrics.prompt_tokens / 1000) * 0.0015
        gpt35_completion_cost = (metrics.completion_tokens / 1000) * 0.002
        cost_table.add_row(
            "OpenAI", "gpt-3.5-turbo", f"${gpt35_prompt_cost + gpt35_completion_cost:.4f}"
        )

        console.print(cost_table)


if __name__ == "__main__" and app is not None:
    app()
