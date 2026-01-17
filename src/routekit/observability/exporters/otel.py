"""OpenTelemetry trace exporter."""

from pydantic import BaseModel, Field

from routekit.observability.trace import Trace


class OTELExporter(BaseModel):
    """Exports traces to OpenTelemetry format.

    TODO: Implement OpenTelemetry export for integration with observability platforms.
    """

    endpoint: str | None = Field(default=None, description="OTEL collector endpoint")
    headers: dict[str, str] = Field(default_factory=dict, description="Export headers")

    async def export(self, trace: Trace) -> None:
        """Export trace to OpenTelemetry.

        Args:
            trace: Trace to export

        Raises:
            NotImplementedError: Not yet implemented
        """
        raise NotImplementedError("OTEL exporter not yet implemented")
