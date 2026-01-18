"""Built-in tools for RouteKit."""

from pathlib import Path

from pydantic import BaseModel, Field

from routekit.core.errors import ToolError
from routekit.core.tool import Tool, ToolPermission


class EchoInput(BaseModel):
    """Input for EchoTool."""

    message: str = Field(..., description="Message to echo")


class EchoOutput(BaseModel):
    """Output for EchoTool."""

    echoed: str = Field(..., description="Echoed message")


class EchoTool(Tool):
    """Echo tool for testing.

    Simply echoes back the input message. Useful for testing and debugging.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="echo",
            description="Echo back a message (useful for testing)",
            input_model=EchoInput,
            output_model=EchoOutput,
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Echo the input message.

        Args:
            input: EchoInput instance

        Returns:
            EchoOutput instance
        """
        if not isinstance(input, EchoInput):
            raise ToolError("Invalid input type for EchoTool")
        return EchoOutput(echoed=input.message)


class HttpGetInput(BaseModel):
    """Input for HttpGetTool."""

    url: str = Field(..., description="URL to fetch")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")


class HttpGetOutput(BaseModel):
    """Output for HttpGetTool."""

    status_code: int = Field(..., description="HTTP status code")
    headers: dict[str, str] = Field(..., description="Response headers")
    body: str = Field(..., description="Response body")


class HttpGetTool(Tool):
    """HTTP GET tool.

    Requires NETWORK permission. Redacts 'api_key' and 'authorization' from headers.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="http_get",
            description="Perform HTTP GET request",
            input_model=HttpGetInput,
            output_model=HttpGetOutput,
            permissions=[ToolPermission.NETWORK],
            redact_fields=["api_key", "authorization"],
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Execute HTTP GET request.

        Args:
            input: HttpGetInput instance

        Returns:
            HttpGetOutput instance

        Raises:
            ToolError: If request fails
        """
        if not isinstance(input, HttpGetInput):
            raise ToolError("Invalid input type for HttpGetTool")

        try:
            # Try to import httpx (optional dependency)
            try:
                import httpx
            except ImportError:
                raise ToolError(
                    "httpx is required for HttpGetTool. Install with: pip install httpx"
                ) from None

            async with httpx.AsyncClient(timeout=input.timeout) as client:
                response = await client.get(input.url, headers=input.headers)
                return HttpGetOutput(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=response.text,
                )
        except Exception as e:
            raise ToolError(f"HTTP GET failed: {e}") from e


class FileReadInput(BaseModel):
    """Input for FileReadTool."""

    path: str = Field(..., description="File path to read")
    encoding: str = Field(default="utf-8", description="File encoding")


class FileReadOutput(BaseModel):
    """Output for FileReadTool."""

    content: str = Field(..., description="File content")
    size: int = Field(..., description="File size in bytes")


class FileReadTool(Tool):
    """File read tool.

    Requires FILESYSTEM permission. Reads file content.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self) -> None:
        super().__init__(
            name="file_read",
            description="Read content from a file",
            input_model=FileReadInput,
            output_model=FileReadOutput,
            permissions=[ToolPermission.FILESYSTEM],
        )

    async def run(self, input: BaseModel) -> BaseModel:
        """Read file content.

        Args:
            input: FileReadInput instance

        Returns:
            FileReadOutput instance

        Raises:
            ToolError: If file read fails
        """
        if not isinstance(input, FileReadInput):
            raise ToolError("Invalid input type for FileReadTool")

        try:
            file_path = Path(input.path)
            if not file_path.exists():
                raise ToolError(f"File not found: {input.path}")
            if not file_path.is_file():
                raise ToolError(f"Path is not a file: {input.path}")

            content = file_path.read_text(encoding=input.encoding)
            size = file_path.stat().st_size

            return FileReadOutput(content=content, size=size)
        except Exception as e:
            raise ToolError(f"File read failed: {e}") from e
