from decimal import Decimal

import pytest

from aigrader_proto.automation import AutomationBlocked, AutomationContext, PauseController, Point, SafeWebAutomation
from aigrader_proto.models import GradeResult


def result(*, review: bool = False) -> GradeResult:
    return GradeResult((), (), Decimal("1"), Decimal("1"), review, "模糊" if review else None, "ok")


@pytest.mark.parametrize(
    "context",
    [
        AutomationContext(False, True, True),
        AutomationContext(True, False, True),
        AutomationContext(True, True, False),
    ],
)
def test_invalid_context_blocks_before_importing_gui(context: AutomationContext) -> None:
    with pytest.raises(AutomationBlocked):
        SafeWebAutomation(PauseController()).submit(Point(1, 1), result(), context)


def test_need_review_blocks_submit() -> None:
    with pytest.raises(AutomationBlocked, match="review"):
        SafeWebAutomation(PauseController()).submit(
            Point(1, 1), result(review=True), AutomationContext(True, True, True)
        )


def test_pause_blocks_submit() -> None:
    pause = PauseController()
    pause.pause()
    with pytest.raises(AutomationBlocked, match="paused"):
        SafeWebAutomation(pause).submit(Point(1, 1), result(), AutomationContext(True, True, True))


def test_pause_between_click_and_typing_blocks_remaining_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    pause = PauseController()

    class FakeGui:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def click(self, x: int, y: int) -> None:
            self.actions.append("click")
            pause.pause()

        def hotkey(self, *keys: str) -> None:
            self.actions.append("hotkey")

        def write(self, value: str, interval: float) -> None:
            self.actions.append("write")

    fake = FakeGui()
    monkeypatch.setattr(SafeWebAutomation, "_pyautogui", staticmethod(lambda: fake))
    with pytest.raises(AutomationBlocked):
        SafeWebAutomation(pause).enter_score(Point(1, 1), result(), AutomationContext(True, True, True))
    assert fake.actions == ["click"]
