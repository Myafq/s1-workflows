from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import DecisionModelError, ModelInputTooLargeError


class JevError(DecisionModelError):
    """The Jev request failed or returned an invalid response."""


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    probabilities: dict[str, float]
    confidence: float
    legend: dict[str, Any]


@dataclass(frozen=True)
class NoulAnswer:
    probability: float


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


class DecisionClient(Protocol):
    def evaluate(
        self,
        *,
        state: str | dict[str, Any] | list[Any],
        questions: dict[str, dict[str, Any]],
        model: str = "jev-latest",
    ) -> dict[str, Answer]:
        ...


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


def parse_answers(
    decoded: Any,
    *,
    service: str,
    error_type: type[DecisionModelError],
) -> dict[str, Answer]:
    try:
        raw_answers = decoded["answers"]
    except (KeyError, TypeError) as error:
        raise error_type(f"{service} returned an invalid response") from error

    if not isinstance(raw_answers, dict):
        raise error_type(f"{service} returned an invalid answers object")

    answers: dict[str, Answer] = {}
    for question_id, raw_answer in raw_answers.items():
        if not isinstance(raw_answer, dict):
            raise error_type(f"{service} returned an invalid answer for '{question_id}'")
        answer_type = raw_answer.get("type")
        try:
            if answer_type == "choice":
                answers[question_id] = ChoiceAnswer(
                    choice=str(raw_answer["choice"]),
                    probabilities=_probabilities(raw_answer["probabilities"]),
                    confidence=_probability(raw_answer["confidence"], "confidence"),
                )
            elif answer_type == "score":
                answers[question_id] = ScoreAnswer(
                    score=float(raw_answer["score"]),
                    probabilities=_probabilities(raw_answer["probabilities"]),
                    confidence=_probability(raw_answer["confidence"], "confidence"),
                    legend={str(key): value for key, value in raw_answer["legend"].items()},
                )
            elif answer_type == "noul":
                answers[question_id] = NoulAnswer(
                    probability=_probability(raw_answer["noul"], "noul")
                )
            else:
                raise error_type(
                    f"{service} returned unknown answer type '{answer_type}' for '{question_id}'"
                )
        except (KeyError, TypeError, ValueError) as error:
            raise error_type(
                f"{service} returned an invalid answer for '{question_id}'"
            ) from error
    return answers


def _probabilities(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise TypeError("probabilities must be an object")
    return {str(key): _probability(item, "probability") for key, item in value.items()}


def _probability(value: Any, name: str) -> float:
    number = float(value)
    if not 0 <= number <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return number
