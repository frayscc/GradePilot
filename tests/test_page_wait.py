from __future__ import annotations

import pytest

from app.core.safety import SafetyController
from app.core.screenshot import VisualSignature
from app.data.calibration import CalibrationProfile, Point, Region
from app.platforms.base import PageSnapshot, PageTransitionError
from app.platforms.zhixue import ZhixuePlatform


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SignatureCapture:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)

    def signature(self, region: Region, **kwargs) -> VisualSignature:
        return VisualSignature((next(self.values),))


def profile(*, marker: bool = False) -> CalibrationProfile:
    return CalibrationProfile(
        Region(10, 10, 100, 80), Point(200, 100), Point(240, 100), Point(60, 5) if marker else None
    )


def test_wait_next_requires_change_then_stability() -> None:
    clock = FakeClock()
    # Each snapshot consumes answer then button. The answer region changes while
    # loading, may return to identical content, then remains stable for three polls.
    capture = SignatureCapture([100, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    platform = ZhixuePlatform(
        profile(), capture, None, next_page_timeout=2, poll_interval=0.25,
        clock=clock.clock, sleeper=clock.sleep,
    )
    before = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)))
    platform.wait_next(before, SafetyController())
    assert clock.now == 1.0


def test_wait_next_stops_if_no_visual_transition() -> None:
    clock = FakeClock()
    capture = SignatureCapture([0, 0] * 4)
    platform = ZhixuePlatform(
        profile(), capture, None, next_page_timeout=1, poll_interval=0.25,
        clock=clock.clock, sleeper=clock.sleep,
    )
    before = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)))
    with pytest.raises(PageTransitionError, match="防重复提交"):
        platform.wait_next(before, SafetyController())


def test_submit_button_hover_alone_is_not_a_page_transition() -> None:
    clock = FakeClock()
    capture = SignatureCapture([0, 100, 0, 0, 0, 0, 0, 0])
    platform = ZhixuePlatform(
        profile(), capture, None, next_page_timeout=1, poll_interval=0.25,
        clock=clock.clock, sleeper=clock.sleep,
    )
    before = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)))
    with pytest.raises(PageTransitionError):
        platform.wait_next(before, SafetyController())


def test_progress_marker_allows_identical_answer_to_advance() -> None:
    clock = FakeClock()
    # With a marker, each snapshot consumes marker, answer, button.
    capture = SignatureCapture([100, 0, 0] * 4)
    platform = ZhixuePlatform(
        profile(marker=True), capture, None, next_page_timeout=2, poll_interval=0.25,
        clock=clock.clock, sleeper=clock.sleep,
    )
    before = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)), VisualSignature((0,)))
    platform.wait_next(before, SafetyController())
    assert clock.now == 0.75


def test_old_ai_result_is_blocked_if_answer_changed() -> None:
    capture = SignatureCapture([100, 0])
    platform = ZhixuePlatform(profile(), capture, None)
    before = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)))
    with pytest.raises(PageTransitionError, match="旧结果"):
        platform.assert_same_answer(before)
