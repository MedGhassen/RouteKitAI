"""Evaluation runner for agent testing."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from routekit.core.runtime import Runtime
from routekit.evals.dataset import Dataset
from routekit.evals.metrics import Metric


class EvalResult(BaseModel):
    """Result for a single evaluation example."""

    example_id: str = Field(..., description="Example ID")
    input: str = Field(..., description="Input prompt")
    expected_output: str | None = Field(default=None, description="Expected output")
    actual_output: str = Field(..., description="Actual output")
    scores: dict[str, float] = Field(default_factory=dict, description="Metric scores")
    trace_id: str | None = Field(default=None, description="Trace ID")
    passed: bool = Field(default=False, description="Whether evaluation passed")
    error: str | None = Field(default=None, description="Error if evaluation failed")


class EvalReport(BaseModel):
    """Evaluation report with aggregated results."""

    dataset_name: str = Field(..., description="Dataset name")
    agent_name: str = Field(..., description="Agent name")
    total_examples: int = Field(..., description="Total number of examples")
    passed: int = Field(..., description="Number of passed examples")
    failed: int = Field(..., description="Number of failed examples")
    errors: int = Field(..., description="Number of errors")
    average_scores: dict[str, float] = Field(
        default_factory=dict, description="Average scores per metric"
    )
    results: list[EvalResult] = Field(default_factory=list, description="Individual results")


class EvalRunner(BaseModel):
    """Runner for evaluating agents on datasets."""

    runtime: Runtime = Field(..., description="Runtime for agent execution")
    metrics: list[Metric] = Field(default_factory=list, description="Metrics to compute")
    regression_mode: bool = Field(
        default=False, description="Enable regression mode (compare to baseline)"
    )
    baseline_dir: Path | None = Field(default=None, description="Directory with baseline traces")

    async def run(self, agent_name: str, dataset: Dataset, **kwargs: Any) -> EvalReport:
        """Run evaluation on a dataset.

        Args:
            agent_name: Name of agent to evaluate
            dataset: Evaluation dataset
            **kwargs: Additional parameters for agent execution

        Returns:
            EvalReport with results
        """
        if agent_name not in self.runtime.agents:
            raise ValueError(f"Agent '{agent_name}' not found in runtime")

        results: list[EvalResult] = []
        passed = 0
        failed = 0
        errors = 0

        for example in dataset.examples:
            try:
                # Execute agent
                result = await self.runtime.run(agent_name, example.input, **kwargs)
                actual_output = result.output.content

                # Compute scores
                scores: dict[str, float] = {}
                for metric in self.metrics:
                    score = metric.score(example.expected_output, actual_output)
                    scores[metric.name] = score

                # Check if passed (at least one metric must score > 0)
                passed_example = any(score > 0 for score in scores.values()) if scores else False

                # Regression mode: compare to baseline
                if self.regression_mode and self.baseline_dir:
                    baseline_result = await self._load_baseline_result(example.id)
                    if baseline_result:
                        if baseline_result.actual_output != actual_output:
                            # Output changed - mark as regression
                            passed_example = False
                            scores["regression"] = 0.0
                        else:
                            scores["regression"] = 1.0

                if passed_example:
                    passed += 1
                else:
                    failed += 1

                eval_result = EvalResult(
                    example_id=example.id,
                    input=example.input,
                    expected_output=example.expected_output,
                    actual_output=actual_output,
                    scores=scores,
                    trace_id=result.trace_id,
                    passed=passed_example,
                )
                results.append(eval_result)

            except Exception as e:
                errors += 1
                eval_result = EvalResult(
                    example_id=example.id,
                    input=example.input,
                    expected_output=example.expected_output,
                    actual_output="",
                    error=str(e),
                    passed=False,
                )
                results.append(eval_result)

        # Compute average scores
        average_scores: dict[str, float] = {}
        if results:
            metric_names: set[str] = set()
            for eval_result in results:
                metric_names.update(eval_result.scores.keys())

            for metric_name in metric_names:
                scores_list = [r.scores.get(metric_name, 0.0) for r in results if r.error is None]
                if scores_list:
                    average_scores[metric_name] = sum(scores_list) / len(scores_list)

        return EvalReport(
            dataset_name=dataset.name,
            agent_name=agent_name,
            total_examples=len(dataset.examples),
            passed=passed,
            failed=failed,
            errors=errors,
            average_scores=average_scores,
            results=results,
        )

    async def _load_baseline_result(self, example_id: str) -> EvalResult | None:
        """Load baseline result for regression comparison.

        Args:
            example_id: Example ID

        Returns:
            Baseline result or None
        """
        if not self.baseline_dir:
            return None

        baseline_file = self.baseline_dir / f"{example_id}.json"
        if not baseline_file.exists():
            return None

        try:
            with open(baseline_file, encoding="utf-8") as f:
                data = json.load(f)
                return EvalResult(**data)
        except Exception:
            return None

    def save_baseline(self, report: EvalReport, output_dir: Path) -> None:
        """Save evaluation results as baseline for regression testing.

        Args:
            report: Evaluation report
            output_dir: Directory to save baseline results
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for result in report.results:
            if result.error is None:
                baseline_file = output_dir / f"{result.example_id}.json"
                with open(baseline_file, "w", encoding="utf-8") as f:
                    json.dump(result.model_dump(), f, indent=2)
