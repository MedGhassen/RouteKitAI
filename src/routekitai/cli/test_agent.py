"""CLI command for testing agents."""

import asyncio
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError as e:
    raise ImportError("CLI dependencies not installed. Install with: pip install typer rich") from e

from routekitai.core.agent import Agent
from routekitai.core.runtime import Runtime
from routekitai.core.tools import EchoTool
from routekitai.providers.local import FakeModel

app = typer.Typer(name="test-agent", help="Run sanity checks on RouteKit agents")
console = Console()


def test_command(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Run a battery of sanity checks on RouteKit agents.

    Tests basic agent functionality, tool execution, tracing, and replay.

    Examples:
        routekit test-agent
        routekit test-agent --verbose
    """

    async def _run_tests() -> None:
        console.print("[bold]Running RouteKit agent sanity checks...[/bold]\n")

        tests_passed = 0
        tests_failed = 0
        test_results = []

        # Test 1: Basic agent creation
        console.print("[cyan]Test 1: Agent creation[/cyan]")
        try:
            model = FakeModel(name="test")
            model.add_response("Hello, I'm a test agent!")
            agent = Agent(name="test_agent", model=model, tools=[EchoTool()])
            test_results.append(("Agent creation", True, ""))
            tests_passed += 1
            if verbose:
                console.print("  [green]✓[/green] Agent created successfully")
        except Exception as e:
            test_results.append(("Agent creation", False, str(e)))
            tests_failed += 1
            console.print(f"  [red]✗[/red] Failed: {e}")

        # Test 2: Agent execution
        console.print("\n[cyan]Test 2: Agent execution[/cyan]")
        try:
            model = FakeModel(name="test")
            model.add_response("Test response")
            agent = Agent(name="test_agent", model=model, tools=[])
            result = await agent.run("Test prompt")
            assert result.output.content == "Test response"
            assert result.trace_id is not None
            test_results.append(("Agent execution", True, ""))
            tests_passed += 1
            if verbose:
                console.print("  [green]✓[/green] Agent executed successfully")
                console.print(f"  [dim]    Output: {result.output.content}[/dim]")
                console.print(f"  [dim]    Trace ID: {result.trace_id}[/dim]")
        except Exception as e:
            test_results.append(("Agent execution", False, str(e)))
            tests_failed += 1
            console.print(f"  [red]✗[/red] Failed: {e}")

        # Test 3: Tool execution
        console.print("\n[cyan]Test 3: Tool execution[/cyan]")
        try:
            model = FakeModel(name="test")
            model.add_response(
                {
                    "content": "Calling echo",
                    "tool_calls": [
                        {"id": "call_1", "name": "echo", "arguments": {"message": "test"}}
                    ],
                }
            )
            model.add_response("Tool executed")
            agent = Agent(name="test_agent", model=model, tools=[EchoTool()])
            result = await agent.run("Use the echo tool")
            test_results.append(("Tool execution", True, ""))
            tests_passed += 1
            if verbose:
                console.print("  [green]✓[/green] Tool executed successfully")
                console.print(f"  [dim]    Output: {result.output.content}[/dim]")
        except Exception as e:
            test_results.append(("Tool execution", False, str(e)))
            tests_failed += 1
            console.print(f"  [red]✗[/red] Failed: {e}")

        # Test 4: Tracing
        console.print("\n[cyan]Test 4: Trace generation[/cyan]")
        try:
            trace_dir = Path(".routekit") / "traces" / "test"
            model = FakeModel(name="test")
            model.add_response("Traced response")
            agent = Agent(name="test_agent", model=model, tools=[], trace_dir=trace_dir)
            result = await agent.run("Test trace")

            # Check if trace file exists
            from routekitai.observability.exporters.jsonl import JSONLExporter

            exporter = JSONLExporter(output_dir=trace_dir)
            trace = await exporter.load(result.trace_id)
            assert trace is not None
            assert len(trace.events) > 0
            test_results.append(("Trace generation", True, ""))
            tests_passed += 1
            if verbose:
                console.print("  [green]✓[/green] Trace generated successfully")
                console.print(f"  [dim]    Events: {len(trace.events)}[/dim]")
        except Exception as e:
            test_results.append(("Trace generation", False, str(e)))
            tests_failed += 1
            console.print(f"  [red]✗[/red] Failed: {e}")

        # Test 5: Replay
        console.print("\n[cyan]Test 5: Trace replay[/cyan]")
        try:
            trace_dir = Path(".routekit") / "traces" / "test"
            model = FakeModel(name="test")
            model.add_response("Replay test")
            agent = Agent(name="test_agent", model=model, tools=[], trace_dir=trace_dir)
            result = await agent.run("Replay test")
            trace_id = result.trace_id

            # Replay
            runtime = Runtime(trace_dir=trace_dir)
            runtime.register_agent(agent)
            replay_result = await runtime.replay(trace_id, "test_agent", verify_output=True)
            assert replay_result.output.content == result.output.content
            test_results.append(("Trace replay", True, ""))
            tests_passed += 1
            if verbose:
                console.print("  [green]✓[/green] Replay successful")
                console.print(
                    f"  [dim]    Output matches: {replay_result.output.content == result.output.content}[/dim]"
                )
        except Exception as e:
            test_results.append(("Trace replay", False, str(e)))
            tests_failed += 1
            console.print(f"  [red]✗[/red] Failed: {e}")

        # Summary
        console.print("\n" + "=" * 50)
        table = Table(title="Test Results", show_header=True, header_style="bold magenta")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Error", style="red")

        for test_name, passed, error in test_results:
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            table.add_row(test_name, status, error or "-")

        console.print(table)
        console.print(f"\n[bold]Total: {tests_passed} passed, {tests_failed} failed[/bold]")

        if tests_failed > 0:
            console.print("\n[red]Some tests failed. Check the output above for details.[/red]")
            raise typer.Exit(1)
        else:
            console.print("\n[green]All tests passed! ✓[/green]")

    asyncio.run(_run_tests())


if __name__ == "__main__" and app is not None:
    app()
