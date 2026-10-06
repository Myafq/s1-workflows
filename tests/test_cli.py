from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jev_workflows.cli import main
from jev_workflows.contracts import (
    AssessmentResult,
    BooleanDecision,
    Classification,
    Score,
)


class FakeModel:
    def assess(self, assessment):
        return AssessmentResult(
            provider="fake",
            model="test",
            scores={"overall_risk": Score(1.0, 0.9, {"1": 1.0})},
            classification=Classification("routine", 0.9, {"routine": 1.0}),
            deeper_review=BooleanDecision(False, 0.1),
            risk_flags={},
        )


class CliTests(unittest.TestCase):
    def test_raw_diff_file_emits_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "change.diff"
            path.write_text("diff --git a/a b/a\n+change\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main([str(path)], model_factory=lambda args: FakeModel())

        self.assertEqual(exit_code, 0)
        decoded = json.loads(output.getvalue())
        self.assertEqual(decoded["schema_version"], "1.0")
        self.assertEqual(decoded["provider"], "fake")

    def test_empty_diff_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.diff"
            path.write_text("", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                exit_code = main([str(path)], model_factory=lambda args: FakeModel())

        self.assertEqual(exit_code, 1)
        self.assertIn("diff must not be empty", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
