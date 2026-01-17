"""JSONL trace exporter."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from routekit.observability.exporters.base import TraceExporter
from routekit.observability.trace import Trace, TraceEvent


class JSONLExporter(TraceExporter, BaseModel):
    """Exports traces to JSONL format.

    Writes one event per line to .routekit/traces/<trace_id>.jsonl
    """

    output_dir: Path = Field(..., description="Output directory for JSONL files")

    def __init__(self, output_dir: Path | str | None = None, **kwargs: Any) -> None:
        """Initialize JSONL exporter.

        Args:
            output_dir: Output directory (defaults to .routekit/traces)
            **kwargs: Additional fields
        """
        if output_dir is None:
            output_dir = Path(".routekit") / "traces"
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)
        super().__init__(output_dir=output_dir, **kwargs)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def export(self, trace: Trace) -> None:
        """Export trace to JSONL file.

        Args:
            trace: Trace to export
        """
        # Ensure directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        trace_file = self.output_dir / f"{trace.trace_id}.jsonl"
        with trace_file.open("w") as f:
            for event in trace.events:
                # Use mode='json' to ensure all data is JSON-serializable
                f.write(json.dumps(event.model_dump(mode='json')) + "\n")

    async def load(self, trace_id: str) -> Trace | None:
        """Load trace from JSONL file.

        Args:
            trace_id: Trace ID to load

        Returns:
            Trace if found, None otherwise
        """
        trace_file = self.output_dir / f"{trace_id}.jsonl"
        if not trace_file.exists():
            return None

        events: list[TraceEvent] = []
        with trace_file.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event_data = json.loads(line)
                events.append(TraceEvent(**event_data))

        if not events:
            return None

        # Extract metadata from run_started event if present
        metadata = {}
        for event in events:
            if event.type == "run_started" and "metadata" in event.data:
                metadata = event.data.get("metadata", {})
                break

        return Trace(trace_id=trace_id, events=events, metadata=metadata)
