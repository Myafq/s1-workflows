from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .contracts import DecisionModelError, ModelInputTooLargeError
from .s1 import Answer, parse_answers


class JevError(DecisionModelError):
    """The Jev request failed or returned an invalid response."""


class JevClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.typesafe.ai",
        timeout: float = 15.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self.api_key = api_key
        self.endpoint = f"{base_url.rstrip('/')}/v1/systemone"
        self.timeout = timeout

    def evaluate(
        self,
        *,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
        model: str = "jev-latest",
    ) -> dict[str, Answer]:
        payload = json.dumps(
            {"state": state, "model": model, "questions": questions}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 400 and "max_tokens_exceeded" in detail:
                raise ModelInputTooLargeError(
                    "Jev input exceeded the model context limit"
                ) from error
            raise JevError(f"Jev returned HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise JevError(f"Jev request failed: {error.reason}") from error

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as error:
            raise JevError("Jev returned an invalid response") from error

        return parse_answers(decoded, service="Jev", error_type=JevError)
