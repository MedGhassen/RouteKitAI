"""Runtime primitive for RouteKit."""

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from routekit.core.agent import Agent
from routekit.core.message import Message


class Runtime(BaseModel):
    """Orchestration runtime for agent workflows."""

    agents: dict[str, Agent] = Field(default_factory=dict, description="Registered agents")
    config: dict[str, Any] = Field(default_factory=dict, description="Runtime configuration")

    def register_agent(self, agent: Agent) -> None:
        """Register an agent with the runtime.

        Args:
            agent: Agent to register
        """
        self.agents[agent.name] = agent

    async def run(
        self,
        agent_name: str,
        message: Message,
        **kwargs: Any,
    ) -> AsyncIterator[Message]:
        """Run an agent and yield messages.

        Args:
            agent_name: Name of the agent to run
            message: Input message
            **kwargs: Additional runtime parameters

        Yields:
            Messages from the agent execution
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} not found")
        agent = self.agents[agent_name]
        # Convert Message to string prompt for agent.run()
        result = await agent.run(message.content, **kwargs)
        yield result.output
