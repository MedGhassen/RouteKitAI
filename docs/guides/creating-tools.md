# Creating tools

Tools are callable capabilities your agent can use. In RouteKitAI they are defined by subclassing `Tool` and implementing `run()` with optional Pydantic input/output models.

## Basic tool

Subclass `Tool`, set `name` and `description`, and implement `run()`:

```python
from pydantic import BaseModel
from routekitai.core.tool import Tool

class GreetInput(BaseModel):
    name: str

class GreetOutput(BaseModel):
    message: str

class GreetTool(Tool):
    name = "greet"
    description = "Greet someone by name"

    async def run(self, input: BaseModel) -> BaseModel:
        assert isinstance(input, GreetInput)
        return GreetOutput(message=f"Hello, {input.name}!")
```

If you don’t use typed input/output, you can use a generic input model or `None` for `input_model`/`output_model` and pass through a simple Pydantic model. The framework uses **input_model** (when set) to validate arguments and to expose a JSON Schema for the model.

## Input and output models

- **`input_model`** — Pydantic model for the tool’s arguments. The model’s JSON schema is used for the model/LLM; arguments are validated before `run()`.
- **`output_model`** — Optional; use for structured return values.

Example with explicit models:

```python
from pydantic import BaseModel, Field
from routekitai.core.tool import Tool

class SearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    limit: int = Field(5, ge=1, le=20)

class SearchOutput(BaseModel):
    results: list[str]
    count: int

class SearchTool(Tool):
    name = "search"
    description = "Search the knowledge base"
    input_model = SearchInput
    output_model = SearchOutput

    async def run(self, input: BaseModel) -> BaseModel:
        inp = SearchInput.model_validate(input)
        # ... do search ...
        return SearchOutput(results=["a", "b"], count=2)
```

The `parameters` property on `Tool` returns the JSON Schema for the tool’s input (derived from `input_model`), which is what gets sent to the LLM.

## Permissions and security

Tools can declare **permissions** so that runtime hooks (e.g. approval gates) can restrict or require approval for certain operations:

```python
from routekitai.core.tool import Tool, ToolPermission

class ApiTool(Tool):
    name = "call_api"
    description = "Call external API"
    permissions = [ToolPermission.NETWORK]
    # ...
```

Permission values: `NETWORK`, `FILESYSTEM`, `DATABASE`, `NONE`.

Use **`redact_fields`** so sensitive fields are redacted in traces:

```python
class ApiTool(Tool):
    name = "call_api"
    description = "Call API with key"
    redact_fields = ["api_key", "Authorization"]
    # ...
```

## Timeout and rate limit

- **`timeout`** — Max seconds for a single tool run.
- **`rate_limit`** — Optional; rate limit (e.g. calls per second) is enforced by the runtime when supported.

## Built-in tools

RouteKitAI includes a few built-in tools in `routekitai.core.tools`:

- **EchoTool** — Echoes a message (useful for demos and tests).
- **HttpGetTool** — HTTP GET request (requires network permission).
- **FileReadTool** — Read a file from the filesystem (filesystem permission).

Use them as references or in examples:

```python
from routekitai.core.tools import EchoTool, FileReadTool, HttpGetTool

agent = Agent(name="agent", model=model, tools=[EchoTool(), FileReadTool()])
```

## Registering tools with an agent

Pass the list of tool instances when creating the agent:

```python
agent = Agent(
    name="my_agent",
    model=model,
    tools=[GreetTool(), SearchTool()],
)
```

You can also restrict which tools an agent can use via **ToolFilter** (allow/deny list) on the agent or via **PolicyHooks** on the runtime; see [Security & Governance](../security-and-governance.md).
