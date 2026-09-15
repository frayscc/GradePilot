from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.ai.schemas import GradeResult


class AutomationBlocked(RuntimeError):
    """Safety conditions forbid further browser input."""


class RunState(str, Enum):
    IDLE = "IDLE"
    CAPTURE = "CAPTURE"
    AI_REQUEST = "AI_REQUEST"
    AI_VALIDATION = "AI_VALIDATION"
    SHOW_RESULT = "SHOW_RESULT"
    OBSERVATION_DELAY = "OBSERVATION_DELAY"
    ENTER_SCORE = "ENTER_SCORE"
    SUBMIT = "SUBMIT"
    WAIT_NEXT = "WAIT_NEXT"
    NEED_REVIEW = "NEED_REVIEW"
    API_ERROR = "API_ERROR"
    PAGE_ERROR = "PAGE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class SubmissionPermit:
    result: GradeResult
    ai_success: bool = True
    score_valid: bool = True


class SafetyController:
    def __init__(self) -> None:
        self._enabled = threading.Event()
        self._paused = threading.Event()
        self._pause_locked = threading.Event()
        self._stopped = threading.Event()

    def enable(self) -> None:
        if self._stopped.is_set():
            raise AutomationBlocked("已停止的自动化不能重新启用")
        self._enabled.set()

    def pause(self) -> None:
        self._paused.set()

    def lock_pause(self) -> None:
        self._paused.set()
        self._pause_locked.set()

    def unlock_pause(self) -> None:
        self._pause_locked.clear()

    def resume(self) -> None:
        if not self._stopped.is_set() and not self._pause_locked.is_set():
            self._paused.clear()

    def stop(self) -> None:
        self._stopped.set()
        self._paused.set()
        self._pause_locked.set()
        self._enabled.clear()

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    @property
    def pause_locked(self) -> bool:
        return self._pause_locked.is_set()

    def guard(self, permit: SubmissionPermit) -> None:
        if self.stopped:
            raise AutomationBlocked("自动化已紧急停止")
        if not self.enabled:
            raise AutomationBlocked("自动化未启用")
        if self.paused:
            raise AutomationBlocked("自动化已暂停")
        if not permit.ai_success or not permit.score_valid:
            raise AutomationBlocked("AI 或分数验证状态无效")
        if permit.result.need_review:
            raise AutomationBlocked("AI 要求人工复核")


def install_hotkeys(safety: SafetyController) -> Callable[[], None]:
    import sys

    if sys.platform != "win32":
        return lambda: None
    import keyboard

    handles = [
        keyboard.add_hotkey("f8", safety.pause),
        keyboard.add_hotkey("f9", safety.resume),
        keyboard.add_hotkey("ctrl+alt+q", safety.stop),
    ]

    def remove() -> None:
        for handle in handles:
            keyboard.remove_hotkey(handle)

    return remove
