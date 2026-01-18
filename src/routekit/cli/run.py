"""CLI command for running agents."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typer
    from rich.console import Console
    from rich.markdown import Markdown
else:
    try:
        import typer
        from rich.console import Console
        from rich.markdown import Markdown
    except ImportError as e:
        raise ImportError(
            "CLI dependencies not installed. Install with: pip install typer rich"
        ) from e

app = typer.Typer(name="run", help="Run an agent with a prompt or script")
console = Console()


async def _run_agent_from_script(script_path: Path) -> None:
    """Run an agent from a Python script.

    Args:
        script_path: Path to Python script
    """
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("agent_script", script_path)
    if spec is None or spec.loader is None:
        console.print(f"[red]Error: Could not load script from {script_path}[/red]")
        return

    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_script"] = module
    spec.loader.exec_module(module)

    # Look for a main() function or agent definition
    if hasattr(module, "main"):
        if asyncio.iscoroutinefunction(module.main):
            await module.main()
        else:
            module.main()
    else:
        console.print("[yellow]Warning: No main() function found in script[/yellow]")


@app.command()  # type: ignore[misc]
def run(
    prompt_or_script: str = typer.Argument(..., help="Prompt string or path to Python script"),
    agent_name: str = typer.Option("default", "--agent", "-a", help="Agent name (if using script)"),
    trace_dir: str | None = typer.Option(
        None, "--trace-dir", "-t", help="Directory for trace files"
    ),
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text, json"),
) -> None:
    """Run an agent with a prompt or execute a Python script.

    Examples:
        routekit run "What is 2+2?"
        routekit run agent_script.py
        routekit run "Hello" --agent my_agent --format json
    """

    script_path = Path(prompt_or_script)
    is_script = script_path.exists() and script_path.suffix == ".py"

    if is_script:
        # Run as script
        console.print(f"[green]Running script: {script_path}[/green]")
        asyncio.run(_run_agent_from_script(script_path))
    else:
        # Run as prompt (requires agent to be registered)
        console.print("[yellow]Note: Direct prompt execution requires a registered agent.[/yellow]")
        console.print("[yellow]Consider using a script or the Python API instead.[/yellow]")
        console.print(f"\n[dim]Prompt: {prompt_or_script}[/dim]")
        console.print("[dim]Agent: {agent_name}[/dim]")
        console.print("\n[blue]Example Python usage:[/blue]")
        console.print(
            Markdown(
                f"""
```python
from routekit import Agent, Runtime
from routekit.providers.local import FakeModel

model = FakeModel(name="test")
agent = Agent(name="my_agent", model=model)

result = await agent.run("{prompt_or_script}")
print(result.output.content)
```
"""
            )
        )


if __name__ == "__main__" and app is not None:
    app()
