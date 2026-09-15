from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CalibrationError(ValueError):
    """Calibration coordinates are missing or invalid."""


@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise CalibrationError("坐标不能为负数")

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise CalibrationError("截图区域位置不能为负，宽高必须大于 0")

    @classmethod
    def from_corners(cls, first: Point, second: Point) -> "Region":
        return cls(min(first.x, second.x), min(first.y, second.y), abs(second.x - first.x), abs(second.y - first.y))

    def around(self, point: Point, radius: int = 16) -> "Region":
        return Region(max(0, point.x - radius), max(0, point.y - radius), radius * 2, radius * 2)

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class CalibrationProfile:
    answer_region: Region
    score_input: Point
    submit_button: Point
    page_marker: Point | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer_region": self.answer_region.as_dict(),
            "score_input": self.score_input.as_dict(),
            "submit_button": self.submit_button.as_dict(),
        }
        if self.page_marker is not None:
            payload["page_marker"] = self.page_marker.as_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Any) -> "CalibrationProfile":
        required = {"answer_region", "score_input", "submit_button"}
        allowed = required | {"page_marker"}
        if not isinstance(payload, dict) or not required.issubset(payload) or not set(payload).issubset(allowed):
            raise CalibrationError("标定文件字段无效")
        region = payload["answer_region"]
        score = payload["score_input"]
        submit = payload["submit_button"]
        marker = payload.get("page_marker")
        if not isinstance(region, dict) or set(region) != {"x", "y", "width", "height"}:
            raise CalibrationError("answer_region 无效")
        if not isinstance(score, dict) or set(score) != {"x", "y"}:
            raise CalibrationError("score_input 无效")
        if not isinstance(submit, dict) or set(submit) != {"x", "y"}:
            raise CalibrationError("submit_button 无效")
        if marker is not None and (not isinstance(marker, dict) or set(marker) != {"x", "y"}):
            raise CalibrationError("page_marker 无效")
        values = [*region.values(), *score.values(), *submit.values(), *(marker.values() if marker else [])]
        if any(type(value) is not int for value in values):
            raise CalibrationError("所有标定坐标必须是整数")
        return cls(Region(**region), Point(**score), Point(**submit), Point(**marker) if marker else None)
