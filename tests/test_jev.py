from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from jev_workflows.contracts import ModelInputTooLargeError
from jev_workflows.jev import ChoiceAnswer, JevClient, NoulAnswer, ScoreAnswer


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "model": "jev-latest",
                "answers": {
                    "risk": {
                        "type": "score",
                        "score": 2.25,
                        "confidence": 0.8,
                        "legend": {"0": "none", "4": "critical"},
                        "probabilities": {"0": 0.1, "2": 0.55, "3": 0.35},
                    },
                    "class": {
                        "type": "choice",
                        "choice": "significant",
                        "probabilities": {"routine": 0.2, "significant": 0.8},
                        "confidence": 0.75,
                    },
                    "review": {"type": "noul", "noul": 0.91},
                },
                "usage": {"input_tokens": 10, "output_tokens": 3},
            }
        ).encode()


class JevClientTests(unittest.TestCase):
    @patch("jev_workflows.jev.urllib.request.urlopen", return_value=FakeResponse())
    def test_evaluate_parses_every_answer_type(self, urlopen) -> None:
        client = JevClient("secret", base_url="https://example.test")
        answers = client.evaluate(
            state={"diff": "change"},
            questions={"risk": {"type": "score", "criteria": ["none", "high"]}},
        )

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://example.test/v1/systemone")
        self.assertEqual(body["model"], "jev-latest")
        self.assertIsInstance(answers["risk"], ScoreAnswer)
        self.assertEqual(answers["risk"].score, 2.25)
        self.assertIsInstance(answers["class"], ChoiceAnswer)
        self.assertIsInstance(answers["review"], NoulAnswer)
        self.assertEqual(answers["review"].probability, 0.91)

    @patch("jev_workflows.jev.urllib.request.urlopen")
    def test_context_limit_response_becomes_retryable_error(self, urlopen) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test/v1/systemone",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"detail":{"error_type":"max_tokens_exceeded"}}'),
        )

        with self.assertRaises(ModelInputTooLargeError):
            JevClient("secret", base_url="https://example.test").evaluate(
                state="large diff",
                questions={"risk": {"type": "score", "criteria": ["low", "high"]}},
            )


if __name__ == "__main__":
    unittest.main()
