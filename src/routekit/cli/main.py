"""Main CLI entry point for RouteKit."""

import sys
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("Error: Typer and Rich are required for CLI. Install with: pip install 'routekit[dev]'")
    sys.exit(1)

from routekit.cli.replay import replay_command
from routekit.cli.run import run as run_command
from routekit.cli.test_agent import test_command
from routekit.cli.trace import trace_command

app = typer.Typer(
    name="routekit",
    help="RouteKit: An agent development + orchestration framework",
    add_completion=False,
)

app.command(name="run")(run_command)
app.command(name="trace")(trace_command)
app.command(name="replay")(replay_command)
app.command(name="test-agent")(test_command)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
