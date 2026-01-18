"""OpenTelemetry trace exporter."""

import json
from typing import Any

from pydantic import BaseModel, Field

from routekit.core.errors import RuntimeError as RouteKitRuntimeError
from routekit.observability.trace import Trace


class OTELExporterError(RouteKitRuntimeError):
    """Error raised by OTEL exporter operations."""

    pass


class OTELExporter(BaseModel):
    """Exports traces to OpenTelemetry format.

    Converts RouteKit traces to OpenTelemetry format and exports them.
    For MVP, exports in JSON format compatible with OTEL collectors.
    """

    endpoint: str | None = Field(default=None, description="OTEL collector endpoint")
    headers: dict[str, str] = Field(default_factory=dict, description="Export headers")

    def _convert_trace_to_otel(self, trace: Trace) -> dict[str, Any]:
        """Convert RouteKit trace to OpenTelemetry format.

        Args:
            trace: RouteKit trace

        Returns:
            OTEL-compatible trace data
        """
        spans = []
        for event in trace.events:
            span = {
                "traceId": trace.trace_id,
                "spanId": event.data.get("step_id", "unknown"),
                "name": event.type,
                "startTimeUnixNano": int(event.timestamp * 1_000_000_000),
                "endTimeUnixNano": int(event.timestamp * 1_000_000_000),
                "attributes": [
                    {"key": "event.type", "value": {"stringValue": event.type}},
                    {"key": "trace.id", "value": {"stringValue": trace.trace_id}},
                ],
            }

            # Add event data as attributes
            for key, value in event.data.items():
                if isinstance(value, (str, int, float, bool)):
                    span["attributes"].append({"key": key, "value": {"stringValue": str(value)}})
                elif isinstance(value, dict):
                    span["attributes"].append(
                        {"key": key, "value": {"stringValue": json.dumps(value)}}
                    )

            spans.append(span)

        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "routekit"}},
                        ]
                    },
                    "scopeSpans": [{"spans": spans}],
                }
            ]
        }

    async def export(self, trace: Trace) -> None:
        """Export trace to OpenTelemetry.

        Args:
            trace: Trace to export

        Raises:
            OTELExporterError: If export fails
        """
        try:
            otel_data = self._convert_trace_to_otel(trace)

            if self.endpoint:
                # Export to OTEL collector endpoint
                try:
                    import httpx

                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            self.endpoint,
                            json=otel_data,
                            headers=self.headers,
                            timeout=10.0,
                        )
                        response.raise_for_status()
                except ImportError:
                    raise OTELExporterError(
                        "httpx is required for OTEL export. Install with: pip install httpx",
                        context={"endpoint": self.endpoint},
                    )
                except Exception as e:
                    raise OTELExporterError(
                        f"Failed to export trace to OTEL endpoint: {e}",
                        context={"endpoint": self.endpoint, "trace_id": trace.trace_id},
                    ) from e
            else:
                # No endpoint specified - just log the OTEL format (for debugging)
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(f"OTEL trace (no endpoint): {json.dumps(otel_data, indent=2)}")
        except Exception as e:
            raise OTELExporterError(
                f"OTEL export failed: {e}", context={"trace_id": trace.trace_id}
            ) from e
