"""Example: Evaluation with regression testing."""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from routekit.core.agent import Agent, RunResult
from routekit.core.runtime import Runtime
from routekit.evals import ContainsMetric, Dataset, EvalRunner, ExactMatchMetric
from routekit.providers.local import FakeModel


class EvalAgent(Agent):
    """Agent for evaluation example."""

    async def run(self, prompt: str, **kwargs: Any) -> RunResult:
        raise NotImplementedError("Use runtime.run() instead")


async def main() -> None:
    """Run evaluation with regression testing."""
    print("Running evaluation with regression testing...")

    # Create model with deterministic responses
    model = FakeModel(name="eval_model")
    model.add_response("The answer is 42")
    model.add_response("RouteKit supports graph orchestration")
    model.add_response("Python is a programming language")

    # Create agent
    agent = EvalAgent(name="eval_agent", model=model, tools=[])

    # Create runtime
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_dir = Path(tmpdir) / "traces"
        runtime = Runtime(trace_dir=trace_dir)
        runtime.register_agent(agent)

        # Create evaluation dataset
        dataset = Dataset(
            name="example_dataset",
            examples=[
                {
                    "id": "example_1",
                    "input": "What is the answer?",
                    "expected_output": "42",
                },
                {
                    "id": "example_2",
                    "input": "What does RouteKit support?",
                    "expected_output": "graph orchestration",
                },
                {
                    "id": "example_3",
                    "input": "What is Python?",
                    "expected_output": "programming language",
                },
            ],
        )

        # Create eval runner with metrics
        runner = EvalRunner(
            runtime=runtime,
            metrics=[
                ExactMatchMetric(case_sensitive=False),
                ContainsMetric(case_sensitive=False),
            ],
        )

        # Run evaluation
        print("\nRunning evaluation...")
        report = await runner.run("eval_agent", dataset)

        print(f"\nEvaluation Report:")
        print(f"  Dataset: {report.dataset_name}")
        print(f"  Agent: {report.agent_name}")
        print(f"  Total: {report.total_examples}")
        print(f"  Passed: {report.passed}")
        print(f"  Failed: {report.failed}")
        print(f"  Errors: {report.errors}")
        print(f"  Average Scores:")
        for metric_name, score in report.average_scores.items():
            print(f"    {metric_name}: {score:.2f}")

        # Save baseline for regression testing
        baseline_dir = Path(tmpdir) / "baseline"
        runner.save_baseline(report, baseline_dir)
        print(f"\nBaseline saved to: {baseline_dir}")

        # Run again with regression mode
        print("\nRunning with regression mode...")
        regression_runner = EvalRunner(
            runtime=runtime,
            metrics=[
                ExactMatchMetric(case_sensitive=False),
                ContainsMetric(case_sensitive=False),
            ],
            regression_mode=True,
            baseline_dir=baseline_dir,
        )

        regression_report = await regression_runner.run("eval_agent", dataset)
        print(f"\nRegression Report:")
        print(f"  Passed: {regression_report.passed}")
        print(f"  Failed: {regression_report.failed}")
        if "regression" in regression_report.average_scores:
            print(f"  Regression score: {regression_report.average_scores['regression']:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
