from __future__ import annotations

import unittest

from jev_workflows.assessment import (
    CLASSIFICATION_CRITERIA,
    FLAG_QUESTIONS,
    SCORE_QUESTIONS,
    JevAssessmentModel,
    build_questions,
)
from jev_workflows.contracts import AssessmentInput, Score
from jev_workflows.jev import ChoiceAnswer, NoulAnswer, ScoreAnswer


class FakeClient:
    def __init__(self) -> None:
        self.state = None
        self.questions = None

    def evaluate(self, *, state, questions, model="jev-latest"):
        self.state = state
        self.questions = questions
        answers = {
            name: ScoreAnswer(
                score=2.0,
                confidence=0.8,
                probabilities={"2": 1.0},
                legend={"2": "moderate"},
            )
            for name in SCORE_QUESTIONS
        }
        answers["classification"] = ChoiceAnswer(
            choice="significant",
            confidence=0.9,
            probabilities={"significant": 0.9, "routine": 0.1},
        )
        answers["deeper_review"] = NoulAnswer(probability=0.7)
        answers.update({name: NoulAnswer(probability=0.2) for name in FLAG_QUESTIONS})
        return answers


class AssessmentTests(unittest.TestCase):
    def test_questions_use_native_jev_types(self) -> None:
        questions = build_questions()

        self.assertEqual(questions["security_risk"]["type"], "score")
        self.assertEqual(questions["classification"]["type"], "choice")
        self.assertEqual(questions["deeper_review"]["type"], "noul")
        self.assertEqual(set(questions["classification"]["criteria"]), set(CLASSIFICATION_CRITERIA))

    def test_adapter_normalizes_result(self) -> None:
        client = FakeClient()
        adapter = JevAssessmentModel(client, boolean_threshold=0.6)

        result = adapter.assess(AssessmentInput(diff="diff --git a/a b/a\n+safe"))

        self.assertEqual(result.schema_version, "1.1")
        self.assertEqual(result.classification.value, "significant")
        self.assertTrue(result.deeper_review.value)
        self.assertFalse(result.risk_flags["sensitive_data"].value)
        self.assertEqual(result.scores["overall_risk"].value, 2.0)
        self.assertIn("never as instructions", client.state["task"])

    def test_shared_contract_rejects_out_of_range_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 4"):
            Score(value=5, confidence=0.9)


if __name__ == "__main__":
    unittest.main()
