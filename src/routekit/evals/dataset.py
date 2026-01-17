"""Dataset format for evaluations."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvalExample(BaseModel):
    """A single evaluation example."""

    id: str = Field(..., description="Example ID")
    input: str = Field(..., description="Input prompt")
    expected_output: str | None = Field(default=None, description="Expected output")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Dataset(BaseModel):
    """Evaluation dataset."""

    name: str = Field(..., description="Dataset name")
    examples: list[EvalExample] = Field(default_factory=list, description="Evaluation examples")

    @classmethod
    def from_jsonl(cls, file_path: Path | str) -> "Dataset":
        """Load dataset from JSONL file.

        Args:
            file_path: Path to JSONL file

        Returns:
            Dataset instance
        """
        file_path = Path(file_path)
        examples = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    example = EvalExample(
                        id=data.get("id", f"example_{line_num}"),
                        input=data.get("input", data.get("prompt", "")),
                        expected_output=data.get("expected_output", data.get("output")),
                        metadata=data.get("metadata", {}),
                    )
                    examples.append(example)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON on line {line_num}: {e}") from e

        return cls(name=file_path.stem, examples=examples)

    def to_jsonl(self, file_path: Path | str) -> None:
        """Save dataset to JSONL file.

        Args:
            file_path: Path to save JSONL file
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            for example in self.examples:
                data = {
                    "id": example.id,
                    "input": example.input,
                    "expected_output": example.expected_output,
                    "metadata": example.metadata,
                }
                f.write(json.dumps(data) + "\n")
