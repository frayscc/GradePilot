from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .models import GradeResult, ValidationError


class AutomationBlocked(RuntimeError):
    """Safety state forbids an input or submit action."""


class PauseController:
    def __init__(self) -> None:
        self._paused = threading.Event()
        self._stopped = threading.Event()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        if not self._stopped.is_set():
            self._paused.clear()

    def stop(self) -> None:
        self._stopped.set()
        self._paused.set()

    @property
    def may_operate(self) -> bool:
        return not self._paused.is_set() and not self._stopped.is_set()


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class AutomationContext:
    enabled: bool
    ai_success: bool
    score_valid: bool


def enable_windows_dpi_awareness() -> str:
    if sys.platform != "win32":
        return "not-windows"
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor-v2"
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
        return "system-aware"


def install_windows_hotkeys(pause: PauseController) -> Callable[[], None]:
    """Register Phase 0 safety hotkeys and return their cleanup callback."""
    if sys.platform != "win32":
        return lambda: None
    import keyboard

    handles = [
        keyboard.add_hotkey("f8", pause.pause),
        keyboard.add_hotkey("f9", pause.resume),
        keyboard.add_hotkey("ctrl+alt+q", pause.stop),
    ]

    def cleanup() -> None:
        for handle in handles:
            keyboard.remove_hotkey(handle)

    return cleanup


class SafeWebAutomation:
    def __init__(self, pause: PauseController) -> None:
        self.pause = pause

    @staticmethod
    def _pyautogui():
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        return pyautogui

    def _check(self, context: AutomationContext, result: GradeResult) -> None:
        if not context.enabled or not context.ai_success or not context.score_valid:
            raise AutomationBlocked("automation safety context is not ready")
        if not self.pause.may_operate:
            raise AutomationBlocked("automation is paused or stopped")
        if result.need_review:
            raise AutomationBlocked("AI requested human review")
        if result.total_score < Decimal("0") or result.total_score > result.max_score:
            raise ValidationError("score became invalid before automation")

    def enter_score(self, point: Point, result: GradeResult, context: AutomationContext) -> None:
        self._check(context, result)
        gui = self._pyautogui()
        gui.click(point.x, point.y)
        self._check(context, result)
        gui.hotkey("ctrl", "a")
        self._check(context, result)
        gui.write(format(result.total_score, "f"), interval=0.05)

    def submit(self, point: Point, result: GradeResult, context: AutomationContext) -> None:
        # Mandatory final gate immediately before the irreversible click.
        self._check(context, result)
        self._pyautogui().click(point.x, point.y)
