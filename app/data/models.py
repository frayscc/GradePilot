from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class TaskValidationError(ValueError):
    """A task file is incomplete or internally inconsistent."""


def as_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TaskValidationError(f"{field} 必须是数字")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TaskValidationError(f"{field} 必须是数字") from exc


def require_exact_keys(payload: dict[str, Any], expected: set[str], name: str) -> None:
    missing = expected - payload.keys()
    extra = payload.keys() - expected
    if missing or extra:
        raise TaskValidationError(f"{name} 字段错误：缺少 {sorted(missing)}，多出 {sorted(extra)}")


def string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TaskValidationError(f"{field} 必须是字符串数组")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class Question:
    text: str
    image_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.text.strip() and self.image_path is None:
            raise TaskValidationError("题目文字和题目图片至少提供一个")
        if self.image_path is not None and not self.image_path.is_file():
            raise TaskValidationError(f"题目图片不存在：{self.image_path}")


@dataclass(frozen=True)
class RubricItem:
    part: str
    max_score: Decimal
    reference_answers: tuple[str, ...]
    criteria: str
    accepted_expressions: tuple[str, ...] = ()
    rejected_expressions: tuple[str, ...] = ()
    require_unit: bool = False
    exact_match: bool = False
    forbid_typos: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.part.strip():
            raise TaskValidationError("评分项 part 不能为空")
        if self.max_score <= 0:
            raise TaskValidationError(f"评分项 {self.part} 满分必须大于 0")
        if not self.reference_answers:
            raise TaskValidationError(f"评分项 {self.part} 至少需要一个参考答案")
        if not self.criteria.strip():
            raise TaskValidationError(f"评分项 {self.part} 的得分标准不能为空")


@dataclass(frozen=True)
class Rubric:
    items: tuple[RubricItem, ...]
    supplemental_rules: str = ""

    def __post_init__(self) -> None:
        if not self.items:
            raise TaskValidationError("至少需要一个评分项")
        parts = [item.part for item in self.items]
        if len(parts) != len(set(parts)):
            raise TaskValidationError("评分项 part 不得重复")


@dataclass(frozen=True)
class Task:
    task_id: str
    name: str
    question_number: str
    max_score: Decimal
    score_step: Decimal
    provider: str
    model: str
    rule_version: int
    question: Question
    rubric: Rubric

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.name.strip() or not self.question_number.strip():
            raise TaskValidationError("task_id、name、question_number 不能为空")
        if self.max_score <= 0 or self.score_step <= 0:
            raise TaskValidationError("满分和分数步长必须大于 0")
        if self.max_score % self.score_step != 0:
            raise TaskValidationError("满分必须是分数步长的整数倍")
        if self.provider != "deepseek":
            raise TaskValidationError("V1 当前仅实现 deepseek provider")
        if not self.model.strip():
            raise TaskValidationError("model 不能为空")
        if self.rule_version < 1:
            raise TaskValidationError("rule_version 必须从 1 开始")
        rubric_max = sum((item.max_score for item in self.rubric.items), Decimal("0"))
        if rubric_max != self.max_score:
            raise TaskValidationError(f"各评分项满分合计 {rubric_max} 与整题满分 {self.max_score} 不一致")

    def to_dict(self, *, base_dir: Path | None = None) -> dict[str, Any]:
        image_path: str | None = None
        if self.question.image_path is not None:
            image_path = str(self.question.image_path)
            if base_dir is not None:
                try:
                    image_path = str(self.question.image_path.relative_to(base_dir.resolve()))
                except ValueError:
                    pass

        def number(value: Decimal) -> int | float:
            return int(value) if value == value.to_integral_value() else float(value)

        return {
            "task_id": self.task_id,
            "name": self.name,
            "question_number": self.question_number,
            "max_score": number(self.max_score),
            "score_step": number(self.score_step),
            "provider": self.provider,
            "model": self.model,
            "rule_version": self.rule_version,
            "question": {"text": self.question.text, "image_path": image_path},
            "rubric": {
                "items": [
                    {
                        "part": item.part,
                        "max_score": number(item.max_score),
                        "reference_answers": list(item.reference_answers),
                        "criteria": item.criteria,
                        "accepted_expressions": list(item.accepted_expressions),
                        "rejected_expressions": list(item.rejected_expressions),
                        "require_unit": item.require_unit,
                        "exact_match": item.exact_match,
                        "forbid_typos": item.forbid_typos,
                        "notes": item.notes,
                    }
                    for item in self.rubric.items
                ],
                "supplemental_rules": self.rubric.supplemental_rules,
            },
        }

    @classmethod
    def from_dict(cls, payload: Any, *, base_dir: Path) -> "Task":
        if not isinstance(payload, dict):
            raise TaskValidationError("任务必须是 JSON 对象")
        require_exact_keys(
            payload,
            {
                "task_id", "name", "question_number", "max_score", "score_step",
                "provider", "model", "rule_version", "question", "rubric",
            },
            "task",
        )
        question_raw = payload["question"]
        if not isinstance(question_raw, dict):
            raise TaskValidationError("question 必须是对象")
        require_exact_keys(question_raw, {"text", "image_path"}, "question")
        if not isinstance(question_raw["text"], str):
            raise TaskValidationError("question.text 必须是字符串")
        image_value = question_raw["image_path"]
        if image_value is not None and not isinstance(image_value, str):
            raise TaskValidationError("question.image_path 必须是字符串或 null")
        image_path = (base_dir / image_value).resolve() if image_value else None
        question = Question(str(question_raw["text"]), image_path)

        rubric_raw = payload["rubric"]
        if not isinstance(rubric_raw, dict):
            raise TaskValidationError("rubric 必须是对象")
        require_exact_keys(rubric_raw, {"items", "supplemental_rules"}, "rubric")
        if not isinstance(rubric_raw["items"], list):
            raise TaskValidationError("rubric.items 必须是数组")
        if not isinstance(rubric_raw["supplemental_rules"], str):
            raise TaskValidationError("rubric.supplemental_rules 必须是字符串")
        item_keys = {
            "part", "max_score", "reference_answers", "criteria", "accepted_expressions",
            "rejected_expressions", "require_unit", "exact_match", "forbid_typos", "notes",
        }
        items: list[RubricItem] = []
        for index, raw in enumerate(rubric_raw["items"], start=1):
            if not isinstance(raw, dict):
                raise TaskValidationError(f"rubric.items[{index}] 必须是对象")
            require_exact_keys(raw, item_keys, f"rubric.items[{index}]")
            for field in ("part", "criteria", "notes"):
                if not isinstance(raw[field], str):
                    raise TaskValidationError(f"rubric.items[{index}].{field} 必须是字符串")
            for flag in ("require_unit", "exact_match", "forbid_typos"):
                if type(raw[flag]) is not bool:
                    raise TaskValidationError(f"rubric.items[{index}].{flag} 必须是布尔值")
            items.append(
                RubricItem(
                    part=str(raw["part"]),
                    max_score=as_decimal(raw["max_score"], f"rubric.items[{index}].max_score"),
                    reference_answers=string_tuple(raw["reference_answers"], "reference_answers"),
                    criteria=str(raw["criteria"]),
                    accepted_expressions=string_tuple(raw["accepted_expressions"], "accepted_expressions"),
                    rejected_expressions=string_tuple(raw["rejected_expressions"], "rejected_expressions"),
                    require_unit=raw["require_unit"],
                    exact_match=raw["exact_match"],
                    forbid_typos=raw["forbid_typos"],
                    notes=str(raw["notes"]),
                )
            )
        for field in ("task_id", "name", "question_number", "provider", "model"):
            if not isinstance(payload[field], str):
                raise TaskValidationError(f"{field} 必须是字符串")
        if type(payload["rule_version"]) is not int:
            raise TaskValidationError("rule_version 必须是整数")
        return cls(
            task_id=payload["task_id"],
            name=payload["name"],
            question_number=payload["question_number"],
            max_score=as_decimal(payload["max_score"], "max_score"),
            score_step=as_decimal(payload["score_step"], "score_step"),
            provider=payload["provider"],
            model=payload["model"],
            rule_version=payload["rule_version"],
            question=question,
            rubric=Rubric(tuple(items), rubric_raw["supplemental_rules"]),
        )
