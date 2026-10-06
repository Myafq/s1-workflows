from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .contracts import DecisionModelError, ModelInputTooLargeError
from .jev import Answer, parse_answers


SUPPORTED_CLEF_MODELS = {"clef", "clef-flash"}


class ClefError(DecisionModelError):
    """The Cloudflare Clef request failed or returned an invalid response."""


class ClefClient:
    def __init__(
        self,
        api_token: str,
        account_id: str,
        *,
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout: float = 15.0,
    ) -> None:
        if not api_token:
            raise ValueError("api_token must not be empty")
        if not account_id:
            raise ValueError("account_id must not be empty")
        self.api_token = api_token
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def evaluate(
        self,
        *,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
        model: str = "clef",
    ) -> dict[str, Answer]:
        if model not in SUPPORTED_CLEF_MODELS:
            supported = ", ".join(sorted(SUPPORTED_CLEF_MODELS))
            raise ValueError(f"unsupported Cloudflare model '{model}'; choose {supported}")

        endpoint = (
            f"{self.base_url}/accounts/{self.account_id}/ai/run/"
            f"@cf/cloudflare/{model}"
        )
        payload = json.dumps(
            {"state": state, "model": model, "questions": questions}
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 413 or "max_tokens_exceeded" in detail:
                raise ModelInputTooLargeError(
                    "Cloudflare Clef input exceeded the request or model limit"
                ) from error
            raise ClefError(
                f"Cloudflare Clef returned HTTP {error.code}: {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise ClefError(f"Cloudflare Clef request failed: {error.reason}") from error

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as error:
            raise ClefError("Cloudflare Clef returned an invalid response") from error

        # Workers AI REST responses use the Cloudflare API result envelope.
        if isinstance(decoded, dict) and "result" in decoded:
            decoded = decoded["result"]
        return parse_answers(
            decoded, service="Cloudflare Clef", error_type=ClefError
        )
