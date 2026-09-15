from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """An AI result is unsafe to use."""


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} must be numeric") from exc


@dataclass(frozen=True)
class GradeRequest:
    image_path: Path
    question_text: str
    rubric_text: str
    max_score: Decimal
    score_step: Decimal

    def __post_init__(self) -> None:
        if not self.image_path.is_file():
            raise ValidationError(f"image does not exist: {self.image_path}")
        if self.max_score <= 0:
            raise ValidationError("max_score must be positive")
        if self.score_step <= 0:
            raise ValidationError("score_step must be positive")


@dataclass(frozen=True)
class PartGrade:
    part: str
    score: Decimal
    max_score: Decimal
    reason: str


@dataclass(frozen=True)
class GradeResult:
    recognized_answers: tuple[dict[str, str], ...]
    grading: tuple[PartGrade, ...]
    total_score: Decimal
    max_score: Decimal
    need_review: bool
    review_reason: str | None
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "recognized_answers": list(self.recognized_answers),
            "grading": [
                {
                    "part": item.part,
                    "score": float(item.score),
                    "max_score": float(item.max_score),
                    "reason": item.reason,
                }
                for item in self.grading
            ],
            "total_score": float(self.total_score),
            "max_score": float(self.max_score),
            "need_review": self.need_review,
            "review_reason": self.review_reason,
            "summary": self.summary,
        }


REQUIRED_RESULT_KEYS = {
    "recognized_answers",
    "grading",
    "total_score",
    "max_score",
    "need_review",
    "review_reason",
    "summary",
}


def parse_grade_result(payload: Any, *, expected_max: Decimal, score_step: Decimal) -> GradeResult:
    if not isinstance(payload, dict):
        raise ValidationError("AI result must be a JSON object")
    missing = REQUIRED_RESULT_KEYS - payload.keys()
    extra = payload.keys() - REQUIRED_RESULT_KEYS
    if missing or extra:
        raise ValidationError(f"result keys invalid; missing={sorted(missing)}, extra={sorted(extra)}")

    answers_raw = payload["recognized_answers"]
    grading_raw = payload["grading"]
    if not isinstance(answers_raw, list) or not isinstance(grading_raw, list):
        raise ValidationError("recognized_answers and grading must be arrays")

    answers: list[dict[str, str]] = []
    for item in answers_raw:
        if not isinstance(item, dict) or set(item) != {"part", "text"}:
            raise ValidationError("each recognized answer needs exactly part and text")
        if not isinstance(item["part"], str) or not isinstance(item["text"], str):
            raise ValidationError("recognized answer fields must be strings")
        answers.append({"part": item["part"], "text": item["text"]})

    grades: list[PartGrade] = []
    for item in grading_raw:
        if not isinstance(item, dict) or set(item) != {"part", "score", "max_score", "reason"}:
            raise ValidationError("each grading item needs exactly part, score, max_score and reason")
        if not isinstance(item["part"], str) or not isinstance(item["reason"], str):
            raise ValidationError("grading part and reason must be strings")
        score = _decimal(item["score"], "grading.score")
        maximum = _decimal(item["max_score"], "grading.max_score")
        if maximum < 0 or score < 0 or score > maximum:
            raise ValidationError("part score is outside its valid range")
        grades.append(PartGrade(item["part"], score, maximum, item["reason"]))

    total = _decimal(payload["total_score"], "total_score")
    maximum = _decimal(payload["max_score"], "max_score")
    if maximum != expected_max:
        raise ValidationError(f"max_score mismatch: expected {expected_max}, got {maximum}")
    if total < 0 or total > maximum:
        raise ValidationError("total_score is outside its valid range")
    if total % score_step != 0:
        raise ValidationError(f"total_score {total} does not match score step {score_step}")
    if grades and sum((item.score for item in grades), Decimal("0")) != total:
        raise ValidationError("total_score does not equal the sum of part scores")
    if grades and sum((item.max_score for item in grades), Decimal("0")) != maximum:
        raise ValidationError("max_score does not equal the sum of part maxima")
    if type(payload["need_review"]) is not bool:
        raise ValidationError("need_review must be boolean")
    review_reason = payload["review_reason"]
    if review_reason is not None and not isinstance(review_reason, str):
        raise ValidationError("review_reason must be string or null")
    if payload["need_review"] and not review_reason:
        raise ValidationError("need_review=true requires review_reason")
    if not isinstance(payload["summary"], str):
        raise ValidationError("summary must be a string")

    return GradeResult(
        recognized_answers=tuple(answers),
        grading=tuple(grades),
        total_score=total,
        max_score=maximum,
        need_review=payload["need_review"],
        review_reason=review_reason,
        summary=payload["summary"],
    )
