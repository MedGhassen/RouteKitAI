"""CLI tools for RouteKit."""

# TODO: Implement CLI commands
try:
    from routekit.cli.replay import replay_command
    from routekit.cli.run import run_command
    from routekit.cli.test_agent import test_command
    from routekit.cli.trace import trace_command

    __all__ = [
        "run_command",
        "trace_command",
        "replay_command",
        "test_command",
    ]
except ImportError:
    # Typer not installed, CLI not available
    __all__ = []
