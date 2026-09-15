from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from app.core.automation import SafeInputController
from app.core.safety import AutomationBlocked, SafetyController, SubmissionPermit
from app.core.screenshot import ScreenCapture
from app.data.calibration import CalibrationProfile, Region

from .base import GradingPlatform, PageSnapshot, PageTransitionError


class ZhixuePlatform(GradingPlatform):
    def __init__(
        self,
        profile: CalibrationProfile,
        capture: ScreenCapture,
        input_controller: SafeInputController,
        *,
        next_page_timeout: float = 12.0,
        poll_interval: float = 0.25,
        change_threshold: float = 0.015,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.profile = profile
        self.capture = capture
        self.input = input_controller
        self.next_page_timeout = next_page_timeout
        self.poll_interval = poll_interval
        self.change_threshold = change_threshold
        self.clock = clock
        self.sleeper = sleeper

    def capture_answer(self, output: Path) -> Path:
        return self.capture.grab(self.profile.answer_region, output)

    def snapshot_page(self) -> PageSnapshot:
        point = self.profile.submit_button
        button_region = Region(max(0, point.x - 18), max(0, point.y - 18), 36, 36)
        marker_signature = None
        if self.profile.page_marker is not None:
            marker = self.profile.page_marker
            marker_region = Region(max(0, marker.x - 70), max(0, marker.y - 20), 140, 40)
            marker_signature = self.capture.signature(marker_region, grid=32)
        return PageSnapshot(
            answer=self.capture.signature(self.profile.answer_region),
            submit_button=self.capture.signature(button_region),
            page_marker=marker_signature,
        )

    def assert_same_answer(self, before: PageSnapshot) -> None:
        current = self.snapshot_page()
        if before.answer.difference_ratio(current.answer) >= self.change_threshold:
            raise PageTransitionError("AI 处理期间学生答案区域已变化，禁止把旧结果填入新页面")

    def enter_score(self, permit: SubmissionPermit) -> None:
        self.input.enter_score(self.profile.score_input, permit.score, permit)

    def submit(self, permit: SubmissionPermit) -> None:
        self.input.submit(self.profile.submit_button, permit)

    def wait_next(self, before: PageSnapshot, safety: SafetyController) -> None:
        deadline = self.clock() + self.next_page_timeout
        changed_at: float | None = None
        stable_polls = 0
        previous = before
        while self.clock() < deadline:
            if safety.stopped or safety.paused:
                raise AutomationBlocked("等待下一份时自动化已暂停或停止")
            current = self.snapshot_page()
            answer_changed = before.answer.difference_ratio(current.answer) >= self.change_threshold
            marker_changed = bool(
                before.page_marker is not None
                and current.page_marker is not None
                and before.page_marker.difference_ratio(current.page_marker) >= self.change_threshold
            )
            if changed_at is None and (answer_changed or marker_changed):
                changed_at = self.clock()
            if changed_at is not None:
                answer_stable = previous.answer.difference_ratio(current.answer) < self.change_threshold
                marker_stable = True
                if previous.page_marker is not None and current.page_marker is not None:
                    marker_stable = previous.page_marker.difference_ratio(current.page_marker) < self.change_threshold
                stable = answer_stable and marker_stable
                stable_polls = stable_polls + 1 if stable else 0
                if self.clock() - changed_at >= 0.5 and stable_polls >= 3:
                    return
            previous = current
            self.sleeper(self.poll_interval)
        raise PageTransitionError("提交后未观察到答案区域或阅卷进度标记发生有效变化，已停止以防重复提交")
