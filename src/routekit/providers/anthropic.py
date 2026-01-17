"""Anthropic Claude model provider."""

from typing import Any, AsyncIterator

from routekit.core.errors import ModelError
from routekit.core.message import Message
from routekit.core.model import Model, ModelResponse, StreamEvent
from routekit.core.tool import Tool


class AnthropicModel(Model):
    """Anthropic Claude model provider.

    TODO: Implement Anthropic API integration with Claude models and tool use.
    """

    api_key: str | None = None
    base_url: str = "https://api.anthropic.com/v1"

    def __init__(self, name: str = "claude-3-opus", provider: str = "anthropic", api_key: str | None = None, base_url: str = "https://api.anthropic.com/v1", **kwargs: Any) -> None:
        """Initialize Anthropic model.

        Args:
            name: Model name
            provider: Provider name
            api_key: Anthropic API key
            base_url: API base URL
            **kwargs: Additional configuration
        """
        super().__init__()
        self.name = name
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with Anthropic model.

        Args:
            messages: Conversation messages
            tools: Optional tools
            stream: Whether to stream
            **kwargs: Additional parameters

        Returns:
            ModelResponse or stream of events

        Raises:
            ModelError: If API call fails
            NotImplementedError: Not yet implemented
        """
        raise NotImplementedError("Anthropic provider not yet implemented")
