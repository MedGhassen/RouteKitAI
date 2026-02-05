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
from routekitai.core.message import MessageRole
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
    output_text = (result.output.content or "").strip()
    if output_text:
        print(output_text)
    else:
        # Fallback when model returned no final text (e.g. after tool use)
        last_with_content = None
        for msg in reversed(result.messages):
            if msg.role == MessageRole.ASSISTANT and (msg.content or "").strip():
                last_with_content = msg.content.strip()
                break
        if last_with_content:
            print(last_with_content)
        else:
            # Show tool results if any
            tool_results = [
                str(msg.tool_result.get("result", msg.content))
                for msg in result.messages
                if msg.role == MessageRole.TOOL and msg.tool_result
            ]
            if tool_results:
                print("(no final text; tool results: ", ", ".join(tool_results), ")")
            else:
                print("(no text output)")

    trace_path = Path(".routekit") / "traces" / f"{result.trace_id}.jsonl"
    print(f"\nTrace ID: {result.trace_id}")
    if trace_path.exists():
        print(f"Trace saved to: {trace_path}")


if __name__ == "__main__":
    asyncio.run(main())
