"""Example: Real agent with Anthropic Claude.

This example runs a live agent using Anthropic's Claude model with tool use.
The agent can answer questions and call tools (e.g. echo) in a ReAct loop.

To run this example:
1. Set your Anthropic API key: export ANTHROPIC_API_KEY='your-api-key-here'
2. (Optional) Set model: export ANTHROPIC_MODEL='claude-sonnet-4-5-20250929'
   If you get a 404 "model not found", list models at https://docs.anthropic.com/en/api/models
   and set ANTHROPIC_MODEL to a model ID available in your account.
3. Install httpx (required by Anthropic provider): pip install httpx
4. Run: python examples/anthropic_agent.py

Note: This example uses real Anthropic API calls and will consume API credits.
   Ensure your Anthropic account has sufficient credits (Plans & Billing).
"""

import asyncio
import os
from pathlib import Path

from routekitai import Agent
from routekitai.core.policies import ReActPolicy
from routekitai.core.tools import EchoTool
from routekitai.providers.anthropic import AnthropicModel


async def main() -> None:
    """Run a real agent with Anthropic Claude."""
    print("Running real agent example with Anthropic Claude...")
    print("=" * 60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Please set it with: export ANTHROPIC_API_KEY='your-api-key-here'"
        )

    # Model: use ANTHROPIC_MODEL env var or a default (see https://docs.anthropic.com/en/api/models)
    model_id = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    model = AnthropicModel(
        name=model_id,
        api_key=api_key,
        provider="anthropic",
    )

    agent = Agent(
        name="claude_agent",
        model=model,
        tools=[EchoTool()],
        policy=ReActPolicy(max_iterations=25),
    )

    print(f"✓ Using Anthropic API (model: {model_id})")
    print("✓ Agent has echo tool available")
    print()

    # Run the agent with a prompt that may trigger tool use
    prompt = (
        "What is 2 + 2? Give the number only. "
        "Then use the echo tool to echo the word 'done' so I know you finished."
    )
    print("Prompt:", prompt)
    print("-" * 60)

    async with model:
        result = await agent.run(prompt)

    print()
    print("=" * 60)
    print("Agent run completed!")
    print("=" * 60)
    print("\nOutput:")
    print(result.output.content)
    print(f"\nTrace ID: {result.trace_id}")

    trace_dir = Path(".routekit") / "traces"
    if trace_dir.exists():
        trace_files = list(trace_dir.glob("*.jsonl"))
        if trace_files:
            latest = max(trace_files, key=lambda p: p.stat().st_mtime)
            print(f"Trace saved to: {latest}")


if __name__ == "__main__":
    asyncio.run(main())
