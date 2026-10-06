from __future__ import annotations

from typing import TypeVar

from .contracts import (
    AssessmentInput,
    AssessmentResult,
    BooleanDecision,
    Classification,
    DecisionModelError,
    Score,
)
from .s1 import Answer, ChoiceAnswer, DecisionClient, NoulAnswer, ScoreAnswer


RISK_LEVELS = [
    "0 - No meaningful risk in this dimension",
    "1 - Low, localized, and easy to detect or reverse",
    "2 - Moderate; warrants normal reviewer attention",
    "3 - High; likely or costly failure needs specialist review or testing",
    "4 - Critical; plausible severe impact, unsafe to merge without mitigation",
]

SCORE_QUESTIONS = {
    "security_risk": "Rate security risk introduced by the change, including authorization, secrets, injection, data exposure, cryptography, and dependency trust.",
    "performance_risk": "Rate performance and scalability risk introduced by the change, including algorithmic cost, I/O, memory, latency, concurrency, and resource exhaustion.",
    "change_impact": "Rate the blast radius of the change, from isolated implementation detail to system-wide behavior, compatibility, data, or operational impact.",
    "maintainability_risk": "Rate code-quality and maintainability risk, including complexity, duplication, unclear contracts, weak error handling, and insufficient testability.",
    "overall_risk": "Rate total merge risk after considering correctness, security, performance, blast radius, reversibility, tests, and operational consequences.",
}

FLAG_QUESTIONS = {
    "authentication_or_authorization": "Does the change affect authentication, authorization, permissions, identity, sessions, or access control?",
    "sensitive_data": "Does the change read, write, expose, transmit, log, or transform secrets, credentials, personal data, or other sensitive data?",
    "public_contract": "Does the change modify a public API, persisted schema, event format, protocol, CLI contract, or other compatibility boundary?",
    "dependency_or_supply_chain": "Does the change add, update, fetch, execute, or alter trust in a dependency, build input, artifact, or external service?",
    "concurrency_or_resource_use": "Does the change materially affect concurrency, locking, retries, caching, resource lifetime, memory, CPU, I/O, or network usage?",
    "deployment_or_migration": "Does the change require a migration, rollout coordination, feature flag, backfill, infrastructure change, or special rollback plan?",
}

CLASSIFICATION_CRITERIA = {
    "trivial": "Mechanical or isolated change with negligible behavior change and negligible review risk",
    "routine": "Normal low-risk change suitable for standard review",
    "significant": "Meaningful behavior or blast radius needing focused review and tests",
    "high_risk": "Material chance of serious failure; needs deep or specialist review before merge",
    "critical": "Plausible severe security, data, availability, or compatibility harm; block pending mitigation",
}


def build_questions() -> dict[str, dict]:
    questions: dict[str, dict] = {
        name: {"type": "score", "instructions": instructions, "criteria": RISK_LEVELS}
        for name, instructions in SCORE_QUESTIONS.items()
    }
    questions["classification"] = {
        "type": "choice",
        "instructions": "Classify the proposed change by the review and merge risk it presents.",
        "criteria": CLASSIFICATION_CRITERIA,
    }
    questions["deeper_review"] = {
        "type": "noul",
        "instructions": "Should this change receive deeper human code review, specialist assessment, or additional validation before merge?",
        "criteria": {
            "true": "Focused analysis beyond a fast standard review is warranted by risk, uncertainty, blast radius, or missing evidence",
            "false": "A normal lightweight review is proportionate to the change",
        },
    }
    questions.update(
        {
            name: {"type": "noul", "instructions": instructions}
            for name, instructions in FLAG_QUESTIONS.items()
        }
    )
    return questions


T = TypeVar("T", bound=Answer)


def _answer(answers: dict[str, Answer], name: str, expected: type[T]) -> T:
    try:
        answer = answers[name]
    except KeyError as error:
        raise DecisionModelError(f"decision model response is missing '{name}'") from error
    if not isinstance(answer, expected):
        raise DecisionModelError(f"decision model returned the wrong answer type for '{name}'")
    return answer


class DecisionAssessmentModel:
    def __init__(
        self,
        client: DecisionClient,
        *,
        model: str,
        provider: str,
        boolean_threshold: float = 0.5,
    ) -> None:
        if not 0 <= boolean_threshold <= 1:
            raise ValueError("boolean_threshold must be between 0 and 1")
        self.client = client
        self.model = model
        self.provider = provider
        self.boolean_threshold = boolean_threshold

    def assess(self, assessment: AssessmentInput) -> AssessmentResult:
        answers = self.client.evaluate(
            state=assessment.to_state(), questions=build_questions(), model=self.model
        )
        scores: dict[str, Score] = {}
        for name in SCORE_QUESTIONS:
            answer = _answer(answers, name, ScoreAnswer)
            scores[name] = Score(
                value=answer.score,
                confidence=answer.confidence,
                probabilities=answer.probabilities,
            )

        classification_answer = _answer(answers, "classification", ChoiceAnswer)
        if classification_answer.choice not in CLASSIFICATION_CRITERIA:
            raise DecisionModelError("decision model returned an unknown classification")

        deep_answer = _answer(answers, "deeper_review", NoulAnswer)
        flags: dict[str, BooleanDecision] = {}
        for name in FLAG_QUESTIONS:
            answer = _answer(answers, name, NoulAnswer)
            flags[name] = self._boolean(answer)

        return AssessmentResult(
            provider=self.provider,
            model=self.model,
            scores=scores,
            classification=Classification(
                value=classification_answer.choice,
                confidence=classification_answer.confidence,
                probabilities=classification_answer.probabilities,
            ),
            deeper_review=self._boolean(deep_answer),
            risk_flags=flags,
        )

    def _boolean(self, answer: NoulAnswer) -> BooleanDecision:
        return BooleanDecision(
            value=answer.probability >= self.boolean_threshold,
            probability=answer.probability,
        )
