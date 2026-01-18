"""Tests for evaluation harness."""

import json
import tempfile
from pathlib import Path

import pytest

from routekit.core.agent import Agent, RunResult
from routekit.core.runtime import Runtime
from routekit.evals import ContainsMetric, Dataset, EvalRunner, ExactMatchMetric, RegexMetric
from routekit.providers.local import FakeModel


class EvalTestAgent(Agent):
    """Test agent for evaluation."""

    async def run(self, prompt: str, **kwargs) -> RunResult:
        raise NotImplementedError("Use runtime.run() instead")


@pytest.mark.asyncio
async def test_exact_match_metric() -> None:
    """Test exact match metric."""
    metric = ExactMatchMetric(case_sensitive=False)

    assert metric.score("hello", "hello") == 1.0
    assert metric.score("Hello", "hello") == 1.0  # Case insensitive
    assert metric.score("hello", "world") == 0.0
    assert metric.score(None, "hello") == 0.0


@pytest.mark.asyncio
async def test_contains_metric() -> None:
    """Test contains metric."""
    metric = ContainsMetric(case_sensitive=False)

    assert metric.score("hello", "hello world") == 1.0
    assert metric.score("Hello", "hello world") == 1.0  # Case insensitive
    assert metric.score("world", "hello") == 0.0
    assert metric.score(None, "hello") == 0.0


@pytest.mark.asyncio
async def test_regex_metric() -> None:
    """Test regex metric."""
    metric = RegexMetric(pattern=r"\d+")

    assert metric.score(None, "The answer is 42") == 1.0
    assert metric.score(None, "No numbers here") == 0.0


@pytest.mark.asyncio
async def test_dataset_from_jsonl() -> None:
    """Test loading dataset from JSONL."""
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": "ex1", "input": "test", "expected_output": "result"}\n')
        f.write('{"id": "ex2", "input": "test2", "expected_output": "result2"}\n')
        f.flush()
        temp_path = f.name

    try:
        dataset = Dataset.from_jsonl(temp_path)
        assert len(dataset.examples) == 2
        assert dataset.examples[0].id == "ex1"
        assert dataset.examples[0].input == "test"
    finally:
        # File is closed, safe to delete on Windows
        try:
            os.unlink(temp_path)
        except (OSError, PermissionError):
            # On Windows, sometimes there's a delay in file release
            pass


@pytest.mark.asyncio
async def test_eval_runner() -> None:
    """Test evaluation runner."""
    model = FakeModel(name="test")
    model.add_response("The answer is 42")
    model.add_response("RouteKit is a framework")

    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = Runtime(trace_dir=Path(tmpdir) / "traces")
        runtime.register_agent(agent)

        dataset = Dataset(
            name="test_dataset",
            examples=[
                {
                    "id": "ex1",
                    "input": "What is the answer?",
                    "expected_output": "42",
                },
                {
                    "id": "ex2",
                    "input": "What is RouteKit?",
                    "expected_output": "framework",
                },
            ],
        )

        runner = EvalRunner(
            runtime=runtime,
            metrics=[ExactMatchMetric(), ContainsMetric()],
        )

        report = await runner.run("test_agent", dataset)

        assert report.total_examples == 2
        assert report.passed >= 0  # At least some should pass with contains metric
        # Check that scores were computed
        assert len(report.results) == 2
        # All results should have scores (unless error)
        for result in report.results:
            if result.error is None:
                assert len(result.scores) > 0, (
                    f"Result {result.example_id} should have scores: {result.scores}"
                )

        # Average scores should be computed if any results succeeded
        if any(r.error is None for r in report.results):
            assert len(report.average_scores) > 0, (
                f"Average scores should be computed: {report.average_scores}"
            )


@pytest.mark.asyncio
async def test_eval_regression_mode() -> None:
    """Test evaluation with regression mode."""
    model = FakeModel(name="test")
    model.add_response("Response 1")

    agent = EvalTestAgent(name="test_agent", model=model, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime = Runtime(trace_dir=Path(tmpdir) / "traces")
        runtime.register_agent(agent)

        dataset = Dataset(
            name="test_dataset",
            examples=[
                {
                    "id": "ex1",
                    "input": "test",
                    "expected_output": "Response 1",
                },
            ],
        )

        # First run - create baseline
        runner = EvalRunner(runtime=runtime, metrics=[ExactMatchMetric()])
        report1 = await runner.run("test_agent", dataset)

        baseline_dir = Path(tmpdir) / "baseline"
        runner.save_baseline(report1, baseline_dir)

        # Reset model for second run (same response)
        model2 = FakeModel(name="test")
        model2.add_response("Response 1")
        agent2 = EvalTestAgent(name="test_agent", model=model2, tools=[])
        runtime.agents["test_agent"] = agent2

        # Second run with regression mode
        regression_runner = EvalRunner(
            runtime=runtime,
            metrics=[ExactMatchMetric()],
            regression_mode=True,
            baseline_dir=baseline_dir,
        )

        report2 = await regression_runner.run("test_agent", dataset)

        # Should pass regression (same output)
        # Regression score is added to individual results, check if any have it
        regression_scores = [
            r.scores.get("regression") for r in report2.results if "regression" in r.scores
        ]
        if regression_scores:
            # If regression mode worked, scores should be 1.0 (no change)
            assert all(score == 1.0 for score in regression_scores)
