"""Azure OpenAI model provider."""

from typing import Any, AsyncIterator

from routekit.core.errors import ModelError
from routekit.core.message import Message
from routekit.core.model import Model, ModelResponse, StreamEvent
from routekit.core.tool import Tool


class AzureOpenAIModel(Model):
    """Azure OpenAI model provider.

    TODO: Implement Azure OpenAI API integration with endpoint and deployment configuration.
    """

    api_key: str | None = None
    endpoint: str | None = None
    deployment_name: str | None = None
    api_version: str = "2024-02-15-preview"

    def __init__(self, name: str = "gpt-4", provider: str = "azure-openai", api_key: str | None = None, endpoint: str | None = None, deployment_name: str | None = None, api_version: str = "2024-02-15-preview", **kwargs: Any) -> None:
        """Initialize Azure OpenAI model.

        Args:
            name: Model name
            provider: Provider name
            api_key: Azure API key
            endpoint: Azure endpoint
            deployment_name: Deployment name
            api_version: API version
            **kwargs: Additional configuration
        """
        super().__init__()
        self.name = name
        self.provider = provider
        self.api_key = api_key
        self.endpoint = endpoint
        self.deployment_name = deployment_name
        self.api_version = api_version

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with Azure OpenAI model.

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
        raise NotImplementedError("Azure OpenAI provider not yet implemented")
