from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import DecisionModelError


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
        model: str,
    ) -> dict[str, Answer]:
        ...


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
