"""Tool primitive for RouteKit."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, Field, create_model

from routekit.core.errors import ToolError

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class ToolPermission(str, Enum):
    """Tool permission types."""

    NETWORK = "network"
    FILESYSTEM = "filesystem"
    DATABASE = "database"
    NONE = "none"


class Tool(BaseModel, ABC):
    """Base class for tools with pydantic input/output models."""

    model_config = {"arbitrary_types_allowed": True}

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_model: type[BaseModel] | None = Field(
        default=None, description="Pydantic model for input validation"
    )
    output_model: type[BaseModel] | None = Field(
        default=None, description="Pydantic model for output validation"
    )
    permissions: list[ToolPermission] = Field(
        default_factory=list, description="Required permissions"
    )
    rate_limit: int | None = Field(
        default=None, description="Rate limit (calls per second)"
    )
    timeout: float | None = Field(default=None, description="Timeout in seconds")
    redact_fields: list[str] = Field(
        default_factory=list, description="Field names to redact in traces (e.g., ['api_key', 'password'])"
    )

    @property
    def parameters(self) -> dict[str, Any]:
        """Generate JSON Schema from input_model.

        Returns:
            JSON Schema dictionary
        """
        if self.input_model is None:
            return {"type": "object", "properties": {}}
        return self.input_model.model_json_schema()

    def redact_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive fields from data (handles nested dicts).

        Args:
            data: Data dictionary to redact

        Returns:
            Data with redacted fields
        """
        if not self.redact_fields:
            return data

        def _redact_recursive(obj: Any) -> Any:
            """Recursively redact fields in nested structures."""
            if isinstance(obj, dict):
                redacted = {}
                for key, value in obj.items():
                    if key in self.redact_fields:
                        redacted[key] = "[REDACTED]"
                    elif isinstance(value, (dict, list)):
                        redacted[key] = _redact_recursive(value)
                    else:
                        redacted[key] = value
                return redacted
            elif isinstance(obj, list):
                return [_redact_recursive(item) for item in obj]
            else:
                return obj

        return _redact_recursive(data)

    @abstractmethod
    async def run(self, input: BaseModel) -> BaseModel:
        """Execute the tool with validated input.

        Args:
            input: Validated input model instance

        Returns:
            Validated output model instance

        Raises:
            ToolError: If tool execution fails
        """
        raise NotImplementedError("Subclasses must implement run")

    async def execute(self, **kwargs: Any) -> Any:
        """Execute tool with raw kwargs (validates input/output).

        Args:
            **kwargs: Raw tool arguments

        Returns:
            Tool output (validated if output_model is set)

        Raises:
            ToolError: If validation or execution fails
        """
        try:
            # Validate input
            if self.input_model is not None:
                input_instance = self.input_model(**kwargs)
            else:
                # Create a minimal model if no input_model
                if not kwargs:
                    # Empty kwargs - create empty model
                    InputModel = create_model("InputModel")
                    input_instance = InputModel()
                else:
                    InputModel = create_model(
                        "InputModel", **{k: (type(v), ...) for k, v in kwargs.items()}
                    )
                    input_instance = InputModel(**kwargs)

            # Execute
            output = await self.run(input_instance)

            # Validate output
            if self.output_model is not None and not isinstance(output, self.output_model):
                raise ToolError(f"Tool {self.name} returned invalid output type")

            return output

        except Exception as e:
            if isinstance(e, ToolError):
                raise
            raise ToolError(f"Tool {self.name} execution failed: {e}") from e
