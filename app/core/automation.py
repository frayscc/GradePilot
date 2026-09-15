from __future__ import annotations

import ctypes
import sys
from decimal import Decimal
from typing import Protocol

from app.core.safety import SafetyController, SubmissionPermit
from app.data.calibration import Point


def enable_windows_dpi_awareness() -> str:
    if sys.platform != "win32":
        return "not-windows"
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor-v2"
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
        return "system-aware"


class InputDriver(Protocol):
    def click(self, x: int, y: int) -> None: ...
    def hotkey(self, *keys: str) -> None: ...
    def write(self, text: str, interval: float) -> None: ...


class PyAutoGuiDriver:
    def __init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        self.gui = pyautogui

    def click(self, x: int, y: int) -> None:
        self.gui.click(x, y)

    def hotkey(self, *keys: str) -> None:
        self.gui.hotkey(*keys)

    def write(self, text: str, interval: float) -> None:
        self.gui.write(text, interval=interval)


class SafeInputController:
    def __init__(self, driver: InputDriver, safety: SafetyController) -> None:
        self.driver = driver
        self.safety = safety

    def enter_score(self, point: Point, score: Decimal, permit: SubmissionPermit) -> None:
        self.safety.guard(permit)
        self.driver.click(point.x, point.y)
        self.safety.guard(permit)
        self.driver.hotkey("ctrl", "a")
        self.safety.guard(permit)
        self.driver.write(format(score, "f"), interval=0.05)

    def submit(self, point: Point, permit: SubmissionPermit) -> None:
        # This is intentionally the final operation: check again immediately before click.
        self.safety.guard(permit)
        self.driver.click(point.x, point.y)
