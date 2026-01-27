"""CLI command for replaying traces."""

import asyncio
from pathlib import Path

try:
    import typer
    from rich.console import Console
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: pip install typer rich") from e

from routekit.core.runtime import Runtime
from routekit.observability.exporters.jsonl import JSONLExporter

app = typer.Typer(name="replay", help="Replay agent execution traces")
console = Console()


def replay_command(
    trace_id: str = typer.Argument(..., help="Trace ID to replay"),
    agent_name: str = typer.Option(..., "--agent", "-a", help="Agent name to use for replay"),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-t", help="Directory containing trace files"
    ),
    verify: bool = typer.Option(
        True, "--verify/--no-verify", help="Verify outputs match original trace"
    ),
) -> None:
    """Replay a trace with deterministic execution.

    Examples:
        routekit replay abc123 --agent my_agent
        routekit replay abc123 --agent my_agent --no-verify
        routekit replay abc123 --agent my_agent --trace-dir ./custom_traces
    """

    async def _replay() -> None:
        # Determine trace directory
        if trace_dir is None:
            trace_dir_path = Path(".routekit") / "traces"
        else:
            trace_dir_path = Path(trace_dir)

        if not trace_dir_path.exists():
            console.print(f"[red]Error: Trace directory not found: {trace_dir_path}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Replaying trace: {trace_id}[/green]")
        console.print(f"[dim]Agent: {agent_name}[/dim]")
        console.print(f"[dim]Trace dir: {trace_dir_path}[/dim]\n")

        # Create runtime and replay
        runtime = Runtime(trace_dir=trace_dir_path)
        result = await runtime.replay(trace_id, agent_name, verify_output=verify)

        console.print("\n[bold]Replay completed[/bold]")
        console.print(f"[green]Output:[/green] {result.output.content}")
        console.print(f"[dim]Trace ID: {result.trace_id}[/dim]")

        if verify:
            # Load original trace for comparison
            exporter = JSONLExporter(output_dir=trace_dir_path)
            original_trace = await exporter.load(trace_id)
            if original_trace:
                original_completed = original_trace.get_events_by_type("run_completed")
                if original_completed:
                    original_result = original_completed[0].data.get("result", {})
                    original_output = original_result.get("output", {}).get("content", "")
                    if original_output != result.output.content:
                        console.print("\n[yellow]⚠ Warning: Output mismatch![/yellow]")
                        console.print(f"[dim]  Original: {original_output}[/dim]")
                        console.print(f"[dim]  Replay:   {result.output.content}[/dim]")
                    else:
                        console.print("\n[green]✓ Output matches original trace[/green]")

    asyncio.run(_replay())


if __name__ == "__main__" and app is not None:
    app()
