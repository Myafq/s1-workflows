from __future__ import annotations

import unittest

from s1_workflows.contracts import (
    AssessmentExecution,
    AssessmentResult,
    BooleanDecision,
    Classification,
    Score,
)
from s1_workflows.github_comment import render_github_comment


class GitHubCommentTests(unittest.TestCase):
    def test_renders_compact_colored_badges_and_tooltips(self) -> None:
        result = AssessmentResult(
            provider="fake",
            model="test-model",
            scores={
                "security_risk": Score(0, 0.95),
                "performance_risk": Score(2, 0.8),
                "overall_risk": Score(4, 0.9),
            },
            classification=Classification("high_risk", 0.82),
            deeper_review=BooleanDecision(True, 0.76),
            risk_flags={
                "sensitive_data": BooleanDecision(True, 0.91),
                "public_contract": BooleanDecision(False, 0.12),
            },
            execution=AssessmentExecution(1000, 2, 48000, "maximum_risk"),
        )

        comment = render_github_comment(result)

        self.assertIn("## S1 risk assessment", comment)
        self.assertIn("label=Classification&message=high+risk&color=orange", comment)
        self.assertIn("label=Security&message=0%2F4&color=brightgreen", comment)
        self.assertIn("label=Performance&message=2%2F4&color=yellow", comment)
        self.assertIn("label=Overall+risk&message=4%2F4&color=red", comment)
        self.assertIn("label=Sensitive+data&message=flagged&color=red", comment)
        self.assertIn("label=Public+contract&message=clear&color=brightgreen", comment)
        self.assertIn("Confidence: 95%.", comment)
        self.assertIn("Probability: 91%.", comment)
        self.assertIn("fake / test-model · 2 diff chunks", comment)

    def test_empty_flags_have_clear_fallback(self) -> None:
        result = AssessmentResult(
            provider="fake",
            model="test",
            scores={},
            classification=Classification("routine", 1),
            deeper_review=BooleanDecision(False, 0),
            risk_flags={},
        )

        comment = render_github_comment(result)

        self.assertIn("_No risk scores returned._", comment)
        self.assertIn("label=Risk+flags&message=none&color=brightgreen", comment)


if __name__ == "__main__":
    unittest.main()
