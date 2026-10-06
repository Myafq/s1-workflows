from __future__ import annotations

import unittest

from s1_workflows.contracts import (
    AssessmentInput,
    AssessmentResult,
    BooleanDecision,
    Classification,
    ModelInputTooLargeError,
    Score,
)
from s1_workflows.runner import AssessmentRunner, aggregate_results, split_diff


def result(
    risk: float,
    classification: str,
    probability: float,
) -> AssessmentResult:
    return AssessmentResult(
        provider="fake",
        model="test",
        scores={"overall_risk": Score(risk, 0.8, {str(round(risk)): 1.0})},
        classification=Classification(classification, 0.8, {classification: 1.0}),
        deeper_review=BooleanDecision(probability >= 0.5, probability),
        risk_flags={"sensitive_data": BooleanDecision(probability >= 0.5, probability)},
    )


class RecordingModel:
    def __init__(self, reject_over: int | None = None) -> None:
        self.reject_over = reject_over
        self.calls: list[AssessmentInput] = []

    def assess(self, assessment: AssessmentInput) -> AssessmentResult:
        self.calls.append(assessment)
        if (
            self.reject_over is not None
            and len(assessment.diff.encode("utf-8")) > self.reject_over
        ):
            raise ModelInputTooLargeError("too large")
        high = "+danger" in assessment.diff
        return result(3.0 if high else 1.0, "high_risk" if high else "routine", 0.9 if high else 0.1)


def file_diff(name: str, body_size: int) -> str:
    return f"diff --git a/{name} b/{name}\n@@ -1 +1 @@\n+" + ("x" * body_size) + "\n"


class RunnerTests(unittest.TestCase):
    def test_small_diff_uses_one_call(self) -> None:
        model = RecordingModel()
        assessment = AssessmentInput(diff=file_diff("small.py", 20))

        output = AssessmentRunner(model, chunk_bytes=1024).assess(assessment)

        self.assertEqual(len(model.calls), 1)
        self.assertEqual(output.execution.chunks_assessed, 1)
        self.assertEqual(output.execution.aggregation, "none")

    def test_large_diff_splits_on_file_boundaries_and_aggregates_maximum(self) -> None:
        model = RecordingModel()
        diff = file_diff("safe.py", 700) + file_diff("danger.py", 700) + "+danger\n"

        output = AssessmentRunner(model, chunk_bytes=1024).assess(
            AssessmentInput(diff=diff)
        )

        self.assertEqual(len(model.calls), 2)
        self.assertEqual(output.scores["overall_risk"].value, 3.0)
        self.assertEqual(output.classification.value, "high_risk")
        self.assertTrue(output.deeper_review.value)
        self.assertEqual(output.execution.aggregation, "maximum_risk")
        self.assertEqual(model.calls[0].chunk_count, 2)

    def test_context_error_halves_threshold_and_retries(self) -> None:
        model = RecordingModel(reject_over=1300)
        diff = file_diff("one.py", 900) + file_diff("two.py", 900)

        output = AssessmentRunner(model, chunk_bytes=2048).assess(
            AssessmentInput(diff=diff)
        )

        self.assertGreater(len(model.calls), output.execution.chunks_assessed)
        self.assertEqual(output.execution.chunk_threshold_bytes, 1024)
        self.assertEqual(output.execution.chunks_assessed, 2)

    def test_split_diff_preserves_small_files(self) -> None:
        first = file_diff("one.py", 600)
        second = file_diff("two.py", 600)

        chunks = split_diff(first + second, 1024)

        self.assertEqual(chunks, [first, second])

    def test_aggregate_rejects_unknown_classification(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown classification"):
            aggregate_results([result(1, "unexpected", 0.2)])


if __name__ == "__main__":
    unittest.main()
