# Providers

RouteKitAI uses a **provider-agnostic** `Model` interface. You can plug in different backends (local fake, OpenAI, Anthropic, Azure, custom) without changing agent code.

## Model interface

All providers implement the same interface:

```python
class Model(ABC):
    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        ...
```

- **messages** — Conversation history (system, user, assistant, tool).
- **tools** — Optional list of tools; the model can return tool calls in the response.
- **stream** — If True, yields `StreamEvent` instead of a single `ModelResponse`.

## FakeModel (local, no API key)

For tests and examples. You preload responses; the model returns them in order.

```python
from routekitai.providers.local import FakeModel

model = FakeModel(name="test")
model.add_response("First reply.")
model.add_response("Second reply.")
# If the model would make two calls, it gets "First reply." then "Second reply."
```

- No network calls; no API key.
- Use in unit tests and in the [getting started](../getting-started.md) flow.

## OpenAI

Uses the OpenAI chat API. Install: `pip install openai` (or use the `optional` extra).

```python
import os
from routekitai.providers.openai import OpenAIChatModel

model = OpenAIChatModel(
    name="gpt-4",
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4",  # or gpt-4o, gpt-3.5-turbo, etc.
)
```

- **api_key** — Prefer environment variable (e.g. `OPENAI_API_KEY`).
- **model** — Model name string passed to the API.

## Anthropic

Uses the Anthropic Messages API (Claude). No extra install beyond RouteKitAI; the provider uses `httpx` (already a dependency).

```python
import os
from routekitai.providers import AnthropicModel

model = AnthropicModel(
    name="claude-3-5-sonnet-20241022",
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
)
```

- **api_key** — Prefer `ANTHROPIC_API_KEY` environment variable.
- **name** — Model name (e.g. `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`).
- **base_url** — Optional; defaults to `https://api.anthropic.com/v1`.

## Azure OpenAI

For Azure-hosted OpenAI models:

```python
from routekitai.providers.azure_openai import AzureOpenAIChatModel  # if available
```

Typically requires endpoint URL and API key (and optionally deployment/model names). See the provider module for parameters.

## Environment variables

Best practice is to **never hardcode** API keys. Use environment variables or a secret manager:

```python
import os
model = OpenAIChatModel(
    name="gpt-4",
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4",
)
```

In production, set `OPENAI_API_KEY` (or the relevant key) in the environment or in your deployment config.

## Custom provider

Implement the `Model` abstract base class:

```python
from routekitai.core.model import Model, ModelResponse
from routekitai.core.message import Message

class MyModel(Model):
    async def chat(self, messages, tools=None, stream=False, **kwargs):
        # Build request, call your backend, return ModelResponse or stream
        return ModelResponse(content="...", usage=...)
```

Then pass an instance to `Agent(model=MyModel(...), ...)`.

## Usage and cost

`ModelResponse` can include a **`usage`** field (prompt/completion/total tokens and optional cost). The trace records this when present; `routekitai trace-analyze` can report token usage and cost for supported providers.
