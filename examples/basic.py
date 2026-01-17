"""Basic example of using RouteKit."""

from routekit import Agent, Message, MessageRole, Model, Runtime, Tool


async def main() -> None:
    """Run a basic RouteKit example."""
    # Define a simple model (placeholder - would need actual implementation)
    model = Model(name="gpt-4", provider="openai", config={})

    # Create a simple tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    calculator = Tool(
        name="add",
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        func=add,
    )

    # Create an agent
    agent = Agent(
        name="assistant",
        model=model,
        tools=[calculator],
        system_prompt="You are a helpful assistant.",
    )

    # Create runtime and register agent
    runtime = Runtime()
    runtime.register_agent(agent)

    # Create a message
    message = Message(role=MessageRole.USER, content="What is 2+2?")

    # Run the agent (this would need actual implementation)
    print(f"Message: {message.content}")
    print(f"Agent: {agent.name}")
    print(f"Tools: {[tool.name for tool in agent.tools]}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
