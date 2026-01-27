"""CLI tools for RouteKit."""

# TODO: Implement CLI commands
try:
    from routekitai.cli.replay import replay_command
    from routekitai.cli.run import run as run_command
    from routekitai.cli.test_agent import test_command
    from routekitai.cli.trace import trace_command

    __all__ = [
        "run_command",
        "trace_command",
        "replay_command",
        "test_command",
    ]
except ImportError:
    # Typer not installed, CLI not available
    __all__ = []
