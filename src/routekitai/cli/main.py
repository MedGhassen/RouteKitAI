"""Main CLI entry point for RouteKit."""

import sys

try:
    import typer
except ImportError:
    print("Error: Typer and Rich are required for CLI. Install with: pip install 'routekit[dev]'")
    sys.exit(1)

from routekitai.cli.replay import replay_command
from routekitai.cli.run import run as run_command
from routekitai.cli.serve import serve_command
from routekitai.cli.test_agent import test_command
from routekitai.cli.trace import trace_command
from routekitai.cli.trace_analyze import analyze_command
from routekitai.cli.trace_search import search_command

app = typer.Typer(
    name="routekit",
    help="RouteKit: An agent development + orchestration framework",
    add_completion=False,
)

app.command(name="run")(run_command)
app.command(name="trace")(trace_command)
app.command(name="trace-analyze")(analyze_command)
app.command(name="trace-search")(search_command)
app.command(name="serve")(serve_command)
app.command(name="replay")(replay_command)
app.command(name="test-agent")(test_command)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
