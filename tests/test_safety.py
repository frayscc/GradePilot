from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.schemas import GradeResult
from app.core.automation import SafeInputController
from app.core.safety import AutomationBlocked, SafetyController, SubmissionPermit
from app.data.calibration import Point


def grade_result(*, need_review: bool = False) -> GradeResult:
    return GradeResult((), (), Decimal("1"), Decimal("1"), need_review, "模糊" if need_review else None, "测试")


class FakeDriver:
    def __init__(self, pause_after_click: SafetyController | None = None) -> None:
        self.actions: list[str] = []
        self.pause_after_click = pause_after_click

    def click(self, x: int, y: int) -> None:
        self.actions.append(f"click:{x},{y}")
        if self.pause_after_click:
            self.pause_after_click.pause()

    def hotkey(self, *keys: str) -> None:
        self.actions.append("hotkey")

    def write(self, text: str, interval: float) -> None:
        self.actions.append(f"write:{text}")


def test_need_review_blocks_all_input() -> None:
    driver = FakeDriver()
    safety = SafetyController()
    safety.enable()
    with pytest.raises(AutomationBlocked, match="复核"):
        SafeInputController(driver, safety).submit(Point(1, 1), SubmissionPermit(grade_result(need_review=True)))
    assert driver.actions == []


def test_pause_between_score_click_and_keyboard_blocks_remainder() -> None:
    safety = SafetyController()
    safety.enable()
    driver = FakeDriver(safety)
    with pytest.raises(AutomationBlocked, match="暂停"):
        SafeInputController(driver, safety).enter_score(Point(5, 6), Decimal("1"), SubmissionPermit(grade_result()))
    assert driver.actions == ["click:5,6"]


def test_submit_has_final_guard() -> None:
    safety = SafetyController()
    safety.stop()
    driver = FakeDriver()
    with pytest.raises(AutomationBlocked, match="停止"):
        SafeInputController(driver, safety).submit(Point(7, 8), SubmissionPermit(grade_result()))
    assert driver.actions == []


def test_automation_must_be_explicitly_enabled() -> None:
    safety = SafetyController()
    driver = FakeDriver()
    with pytest.raises(AutomationBlocked, match="未启用"):
        SafeInputController(driver, safety).submit(Point(7, 8), SubmissionPermit(grade_result()))
    assert driver.actions == []


def test_locked_review_pause_cannot_be_bypassed_by_resume() -> None:
    safety = SafetyController()
    safety.enable()
    safety.lock_pause()
    safety.resume()
    assert safety.paused
    assert safety.pause_locked
    safety.unlock_pause()
    safety.resume()
    assert not safety.paused
