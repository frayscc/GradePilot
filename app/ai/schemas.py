from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.data.models import Task


class ResultValidationError(ValueError):
    """AI output is structurally or numerically unsafe."""


GRADE_RESULT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "recognized_answers", "grading", "total_score", "max_score",
        "need_review", "review_reason", "summary",
    ],
    "properties": {
        "recognized_answers": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["part", "text"],
                "properties": {"part": {"type": "string"}, "text": {"type": "string"}},
            },
        },
        "grading": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["part", "score", "max_score", "reason"],
                "properties": {
                    "part": {"type": "string"}, "score": {"type": "number"},
                    "max_score": {"type": "number"}, "reason": {"type": "string"},
                },
            },
        },
        "total_score": {"type": "number"},
        "max_score": {"type": "number"},
        "need_review": {"type": "boolean"},
        "review_reason": {"type": ["string", "null"]},
        "summary": {"type": "string"},
    },
}


@dataclass(frozen=True)
class GradeRequest:
    task: Task
    answer_image: Path

    def __post_init__(self) -> None:
        if not self.answer_image.is_file():
            raise ResultValidationError(f"学生答案图片不存在：{self.answer_image}")


@dataclass(frozen=True)
class RecognizedAnswer:
    part: str
    text: str


@dataclass(frozen=True)
class PartGrade:
    part: str
    score: Decimal
    max_score: Decimal
    reason: str


@dataclass(frozen=True)
class GradeResult:
    recognized_answers: tuple[RecognizedAnswer, ...]
    grading: tuple[PartGrade, ...]
    total_score: Decimal
    max_score: Decimal
    need_review: bool
    review_reason: str | None
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "recognized_answers": [{"part": item.part, "text": item.text} for item in self.recognized_answers],
            "grading": [
                {"part": item.part, "score": float(item.score), "max_score": float(item.max_score), "reason": item.reason}
                for item in self.grading
            ],
            "total_score": float(self.total_score),
            "max_score": float(self.max_score),
            "need_review": self.need_review,
            "review_reason": self.review_reason,
            "summary": self.summary,
        }


def decimal_value(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ResultValidationError(f"{field} 必须是数字")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ResultValidationError(f"{field} 必须是数字") from exc


def validate_grade_result(payload: Any, task: Task) -> GradeResult:
    if not isinstance(payload, dict):
        raise ResultValidationError("AI 输出必须是 JSON 对象")
    expected_keys = set(GRADE_RESULT_JSON_SCHEMA["required"])
    if set(payload) != expected_keys:
        raise ResultValidationError("AI 输出字段缺失或含未知字段")
    answers_raw, grades_raw = payload["recognized_answers"], payload["grading"]
    if not isinstance(answers_raw, list) or not isinstance(grades_raw, list):
        raise ResultValidationError("recognized_answers 和 grading 必须是数组")

    answers: list[RecognizedAnswer] = []
    for raw in answers_raw:
        if not isinstance(raw, dict) or set(raw) != {"part", "text"}:
            raise ResultValidationError("识别答案字段错误")
        if not isinstance(raw["part"], str) or not isinstance(raw["text"], str):
            raise ResultValidationError("识别答案必须使用字符串")
        answers.append(RecognizedAnswer(raw["part"], raw["text"]))

    rubric_by_part = {item.part: item for item in task.rubric.items}
    expected_parts = set(rubric_by_part)
    answer_parts = [item.part for item in answers]
    if len(answer_parts) != len(set(answer_parts)) or set(answer_parts) != expected_parts:
        raise ResultValidationError("识别答案的评分项必须与任务完全一致且不重复")

    grades: list[PartGrade] = []
    for raw in grades_raw:
        if not isinstance(raw, dict) or set(raw) != {"part", "score", "max_score", "reason"}:
            raise ResultValidationError("逐空评分字段错误")
        part = raw["part"]
        if not isinstance(part, str) or part not in rubric_by_part or not isinstance(raw["reason"], str):
            raise ResultValidationError("逐空评分 part 或 reason 无效")
        score = decimal_value(raw["score"], f"{part}.score")
        maximum = decimal_value(raw["max_score"], f"{part}.max_score")
        if maximum != rubric_by_part[part].max_score or score < 0 or score > maximum:
            raise ResultValidationError(f"评分项 {part} 的分数或满分无效")
        if not raw["reason"].strip():
            raise ResultValidationError(f"评分项 {part} 缺少判分理由")
        grades.append(PartGrade(part, score, maximum, raw["reason"]))
    grade_parts = [item.part for item in grades]
    if len(grade_parts) != len(set(grade_parts)) or set(grade_parts) != expected_parts:
        raise ResultValidationError("逐空评分项必须与任务完全一致且不重复")

    total = decimal_value(payload["total_score"], "total_score")
    maximum = decimal_value(payload["max_score"], "max_score")
    if maximum != task.max_score or total < 0 or total > maximum or total % task.score_step != 0:
        raise ResultValidationError("总分、满分或分数步长无效")
    if sum((item.score for item in grades), Decimal("0")) != total:
        raise ResultValidationError("总分不等于逐空得分合计")
    if type(payload["need_review"]) is not bool:
        raise ResultValidationError("need_review 必须是布尔值")
    reason = payload["review_reason"]
    if payload["need_review"]:
        if not isinstance(reason, str) or not reason.strip():
            raise ResultValidationError("需要复核时必须提供 review_reason")
    elif reason is not None:
        raise ResultValidationError("无需复核时 review_reason 必须为 null")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise ResultValidationError("summary 不能为空")
    return GradeResult(tuple(answers), tuple(grades), total, maximum, payload["need_review"], reason, payload["summary"])
