"""Evaluation metrics for agent outputs."""

import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class Metric(BaseModel, ABC):
    """Base class for evaluation metrics."""

    name: str = Field(..., description="Metric name")

    @abstractmethod
    def score(self, expected: str | None, actual: str) -> float:
        """Score an output against expected output.

        Args:
            expected: Expected output (can be None)
            actual: Actual output

        Returns:
            Score between 0.0 and 1.0
        """
        raise NotImplementedError("Subclasses must implement score")


class ExactMatchMetric(Metric):
    """Exact match metric (case-insensitive)."""

    name: str = Field(default="exact_match", description="Metric name")
    case_sensitive: bool = Field(default=False, description="Whether to be case-sensitive")

    def score(self, expected: str | None, actual: str) -> float:
        """Score based on exact match.

        Args:
            expected: Expected output
            actual: Actual output

        Returns:
            1.0 if exact match, 0.0 otherwise
        """
        if expected is None:
            return 0.0

        if self.case_sensitive:
            return 1.0 if expected.strip() == actual.strip() else 0.0
        else:
            return 1.0 if expected.strip().lower() == actual.strip().lower() else 0.0


class ContainsMetric(Metric):
    """Contains metric (checks if expected is contained in actual)."""

    name: str = Field(default="contains", description="Metric name")
    case_sensitive: bool = Field(default=False, description="Whether to be case-sensitive")

    def score(self, expected: str | None, actual: str) -> float:
        """Score based on substring match.

        Args:
            expected: Expected output (substring to find)
            actual: Actual output

        Returns:
            1.0 if expected is contained in actual, 0.0 otherwise
        """
        if expected is None:
            return 0.0

        if self.case_sensitive:
            return 1.0 if expected.strip() in actual else 0.0
        else:
            return 1.0 if expected.strip().lower() in actual.lower() else 0.0


class RegexMetric(Metric):
    """Regex pattern matching metric."""

    name: str = Field(default="regex", description="Metric name")
    pattern: str = Field(..., description="Regex pattern to match")
    flags: int = Field(default=0, description="Regex flags")

    def __init__(self, **data: Any) -> None:
        """Initialize regex metric."""
        super().__init__(**data)
        self._compiled_pattern = re.compile(self.pattern, self.flags)

    def score(self, expected: str | None, actual: str) -> float:
        """Score based on regex match.

        Args:
            expected: Expected output (not used, pattern is used instead)
            actual: Actual output

        Returns:
            1.0 if pattern matches, 0.0 otherwise
        """
        return 1.0 if self._compiled_pattern.search(actual) else 0.0
