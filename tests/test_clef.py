from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from jev_workflows.clef import ClefClient, ClefError
from jev_workflows.jev import ChoiceAnswer, NoulAnswer, ScoreAnswer


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "success": True,
                "result": {
                    "model": "clef",
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
                },
            }
        ).encode()


class ClefClientTests(unittest.TestCase):
    @patch("jev_workflows.clef.urllib.request.urlopen", return_value=FakeResponse())
    def test_evaluate_calls_workers_ai_and_parses_envelope(self, urlopen) -> None:
        client = ClefClient(
            "secret", "account", base_url="https://api.example.test/client/v4"
        )
        answers = client.evaluate(
            state={"diff": "change"},
            questions={"risk": {"type": "score", "criteria": ["none", "high"]}},
        )

        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(
            request.full_url,
            "https://api.example.test/client/v4/accounts/account/ai/run/@cf/cloudflare/clef",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(body["model"], "clef")
        self.assertIsInstance(answers["risk"], ScoreAnswer)
        self.assertIsInstance(answers["class"], ChoiceAnswer)
        self.assertIsInstance(answers["review"], NoulAnswer)

    def test_rejects_unknown_model_before_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Cloudflare model"):
            ClefClient("secret", "account").evaluate(
                state="change", questions={"risk": {"type": "noul"}}, model="jev-latest"
            )

    @patch("jev_workflows.clef.urllib.request.urlopen")
    def test_cloudflare_http_error_has_provider_context(self, urlopen) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test", 401, "Unauthorized", {}, io.BytesIO(b"denied")
        )

        with self.assertRaisesRegex(ClefError, "Cloudflare Clef returned HTTP 401"):
            ClefClient("secret", "account").evaluate(
                state="change", questions={"risk": {"type": "noul"}}
            )


if __name__ == "__main__":
    unittest.main()
