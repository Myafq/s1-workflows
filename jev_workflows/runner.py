from __future__ import annotations

import re
from dataclasses import replace

from .contracts import (
    AssessmentExecution,
    AssessmentInput,
    AssessmentModel,
    AssessmentResult,
    BooleanDecision,
    ModelInputTooLargeError,
    Score,
)


CLASSIFICATION_ORDER = {
    "trivial": 0,
    "routine": 1,
    "significant": 2,
    "high_risk": 3,
    "critical": 4,
}


class AssessmentRunner:
    def __init__(self, model: AssessmentModel, *, chunk_bytes: int) -> None:
        if chunk_bytes < 1024:
            raise ValueError("chunk_bytes must be at least 1024")
        self.model = model
        self.chunk_bytes = chunk_bytes

    def assess(self, assessment: AssessmentInput) -> AssessmentResult:
        effective_chunk_bytes = self.chunk_bytes
        while True:
            chunks = split_diff(assessment.diff, effective_chunk_bytes)
            try:
                results = [
                    self.model.assess(
                        replace(
                            assessment,
                            diff=chunk,
                            chunk_index=index if len(chunks) > 1 else None,
                            chunk_count=len(chunks) if len(chunks) > 1 else None,
                        )
                    )
                    for index, chunk in enumerate(chunks, start=1)
                ]
                break
            except ModelInputTooLargeError:
                if effective_chunk_bytes <= 1024:
                    raise
                effective_chunk_bytes = max(1024, effective_chunk_bytes // 2)

        result = results[0] if len(results) == 1 else aggregate_results(results)
        return replace(
            result,
            execution=AssessmentExecution(
                input_bytes=len(assessment.diff.encode("utf-8")),
                chunks_assessed=len(chunks),
                chunk_threshold_bytes=effective_chunk_bytes,
                aggregation="none" if len(chunks) == 1 else "maximum_risk",
            ),
        )


def split_diff(diff: str, max_bytes: int) -> list[str]:
    if max_bytes < 1024:
        raise ValueError("max_bytes must be at least 1024")
    if len(diff.encode("utf-8")) <= max_bytes:
        return [diff]

    sections = _file_sections(diff)
    units: list[str] = []
    for section in sections:
        units.extend(_split_section(section, max_bytes))

    chunks: list[str] = []
    current = ""
    current_bytes = 0
    for unit in units:
        unit_bytes = len(unit.encode("utf-8"))
        if current and current_bytes + unit_bytes > max_bytes:
            chunks.append(current)
            current = ""
            current_bytes = 0
        current += unit
        current_bytes += unit_bytes
    if current:
        chunks.append(current)
    return chunks


def aggregate_results(results: list[AssessmentResult]) -> AssessmentResult:
    if not results:
        raise ValueError("at least one assessment result is required")
    first = results[0]
    for result in results[1:]:
        if result.provider != first.provider or result.model != first.model:
            raise ValueError("cannot aggregate results from different models")
        if set(result.scores) != set(first.scores):
            raise ValueError("cannot aggregate results with different score dimensions")
        if set(result.risk_flags) != set(first.risk_flags):
            raise ValueError("cannot aggregate results with different risk flags")

    scores: dict[str, Score] = {
        name: max(
            (result.scores[name] for result in results),
            key=lambda score: (score.value, score.confidence),
        )
        for name in first.scores
    }
    try:
        classification = max(
            (result.classification for result in results),
            key=lambda item: (CLASSIFICATION_ORDER[item.value], item.confidence),
        )
    except KeyError as error:
        raise ValueError(f"unknown classification '{error.args[0]}'") from error

    return AssessmentResult(
        provider=first.provider,
        model=first.model,
        scores=scores,
        classification=classification,
        deeper_review=_maximum_boolean(
            [result.deeper_review for result in results]
        ),
        risk_flags={
            name: _maximum_boolean(
                [result.risk_flags[name] for result in results]
            )
            for name in first.risk_flags
        },
    )


def _maximum_boolean(values: list[BooleanDecision]) -> BooleanDecision:
    return max(values, key=lambda item: item.probability)


def _file_sections(diff: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^diff --git ", diff)]
    if not starts:
        return [diff]
    if starts[0] > 0:
        starts[0] = 0
    return [
        diff[start : starts[index + 1] if index + 1 < len(starts) else len(diff)]
        for index, start in enumerate(starts)
    ]


def _split_section(section: str, max_bytes: int) -> list[str]:
    if len(section.encode("utf-8")) <= max_bytes:
        return [section]

    lines = section.splitlines(keepends=True)
    prefix = lines[0] if lines and lines[0].startswith("diff --git ") else ""
    chunks: list[str] = []
    current = prefix
    current_bytes = len(prefix.encode("utf-8"))
    start = 1 if prefix else 0
    for line in lines[start:]:
        line_bytes = len(line.encode("utf-8"))
        if current != prefix and current_bytes + line_bytes > max_bytes:
            chunks.append(current)
            current = prefix
            current_bytes = len(prefix.encode("utf-8"))
        if current == prefix and current_bytes + line_bytes > max_bytes:
            chunks.extend(_split_oversized_line(prefix, line, max_bytes))
            current = prefix
            current_bytes = len(prefix.encode("utf-8"))
            continue
        current += line
        current_bytes += line_bytes
    if current != prefix:
        chunks.append(current)
    return chunks


def _split_oversized_line(prefix: str, line: str, max_bytes: int) -> list[str]:
    available = max_bytes - len(prefix.encode("utf-8"))
    if available <= 0:
        return [prefix, line]
    pieces: list[str] = []
    remaining = line
    while remaining:
        end = _largest_utf8_prefix(remaining, available)
        pieces.append(prefix + remaining[:end])
        remaining = remaining[end:]
    return pieces


def _largest_utf8_prefix(value: str, max_bytes: int) -> int:
    low, high = 1, len(value)
    best = 1
    while low <= high:
        middle = (low + high) // 2
        if len(value[:middle].encode("utf-8")) <= max_bytes:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return best
