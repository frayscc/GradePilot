import asyncio
from dataclasses import replace
from pathlib import Path

from app.ai.base import AIProvider, ProviderError
from app.ai.schemas import GradeRequest, GradeResult, validate_grade_result
from app.core.automation_session import AutomationSession, AutomationSettings
from app.core.safety import AutomationBlocked, RunState, SafetyController
from app.core.screenshot import VisualSignature
from app.platforms.base import GradingPlatform, PageSnapshot

from .helpers import make_task, valid_result


class SequenceProvider(AIProvider):
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def grade(self, request: GradeRequest) -> GradeResult:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakePlatform(GradingPlatform):
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.snapshot = PageSnapshot(VisualSignature((0,)), VisualSignature((0,)))

    def capture_answer(self, output: Path) -> Path:
        self.actions.append("capture")
        output.write_bytes(b"png")
        return output

    def snapshot_page(self) -> PageSnapshot:
        self.actions.append("snapshot")
        return self.snapshot

    def assert_same_answer(self, before: PageSnapshot) -> None:
        self.actions.append("assert_same")

    def enter_score(self, permit) -> None:
        self.actions.append("enter")

    def submit(self, permit) -> None:
        self.actions.append("submit")

    def wait_next(self, before: PageSnapshot, safety: SafetyController) -> None:
        self.actions.append("wait_next")


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def parsed_result() -> GradeResult:
    return validate_grade_result(valid_result(), make_task())


def active_safety() -> SafetyController:
    safety = SafetyController()
    safety.enable()
    return safety


def test_successful_run_is_strictly_serial_and_submits() -> None:
    platform = FakePlatform()
    session = AutomationSession(
        make_task(), SequenceProvider([parsed_result()]), platform, active_safety(),
        AutomationSettings(observation_delay=0),
    )
    record = asyncio.run(session.run_one(1))
    assert record.submitted is True
    assert record.initial_page == platform.snapshot
    assert platform.actions == ["snapshot", "capture", "assert_same", "enter", "snapshot", "submit", "wait_next"]


def test_need_review_never_enters_score() -> None:
    review = replace(parsed_result(), need_review=True, review_reason="字迹不清")
    platform = FakePlatform()
    record = asyncio.run(
        AutomationSession(
            make_task(), SequenceProvider([review]), platform, active_safety(), AutomationSettings(observation_delay=0)
        ).run_one(1)
    )
    assert record.state == RunState.NEED_REVIEW
    assert record.submitted is False
    assert "enter" not in platform.actions and "submit" not in platform.actions


def test_api_retries_after_two_and_five_seconds() -> None:
    clock = FakeTime()
    provider = SequenceProvider([ProviderError("one"), ProviderError("two"), parsed_result()])
    session = AutomationSession(
        make_task(), provider, FakePlatform(), active_safety(), AutomationSettings(observation_delay=0),
        sleeper=clock.sleep, clock=clock.clock,
    )
    record = asyncio.run(session.run_one(1))
    assert record.submitted is True
    assert provider.calls == 3
    assert round(sum(clock.sleeps), 6) == 7
    assert record.latency_ms == 7000
    assert record.api_success
    assert record.score_entered
    assert record.submit_clicked


def test_three_api_failures_pause_without_input() -> None:
    clock = FakeTime()
    platform = FakePlatform()
    safety = SafetyController()
    safety.enable()
    provider = SequenceProvider([ProviderError("one"), ProviderError("two"), ProviderError("three")])
    session = AutomationSession(
        make_task(), provider, platform, safety, AutomationSettings(observation_delay=0),
        sleeper=clock.sleep, clock=clock.clock,
    )
    record = asyncio.run(session.run_one(1))
    assert record.state == RunState.API_ERROR
    assert safety.paused
    assert "enter" not in platform.actions and "submit" not in platform.actions


def test_pause_after_submit_stops_without_automatic_retry() -> None:
    class PauseAfterSubmitPlatform(FakePlatform):
        def wait_next(self, before: PageSnapshot, safety: SafetyController) -> None:
            self.actions.append("wait_next")
            safety.pause()
            raise AutomationBlocked("paused")

    platform = PauseAfterSubmitPlatform()
    safety = SafetyController()
    safety.enable()
    records = asyncio.run(
        AutomationSession(
            make_task(), SequenceProvider([parsed_result()]), platform, safety,
            AutomationSettings(observation_delay=0),
        ).run_many(2)
    )
    assert len(records) == 1
    assert records[0].state == RunState.PAGE_ERROR
    assert safety.stopped
    assert platform.actions.count("submit") == 1


def test_resume_restarts_same_paper_before_any_submit() -> None:
    safety = active_safety()
    platform = FakePlatform()
    clock = FakeTime()
    paused_once = False

    def controlled_sleep(seconds: float) -> None:
        nonlocal paused_once
        clock.sleep(seconds)
        if not paused_once:
            paused_once = True
            safety.pause()
        elif safety.paused:
            safety.resume()

    session = AutomationSession(
        make_task(), SequenceProvider([parsed_result(), parsed_result()]), platform, safety,
        AutomationSettings(observation_delay=0.1), sleeper=controlled_sleep, clock=clock.clock,
    )
    records = asyncio.run(session.run_many(1))
    assert len(records) == 1 and records[0].submitted
    assert platform.actions.count("capture") == 2
    assert platform.actions.count("submit") == 1


def test_unlimited_run_has_no_hidden_batch_cap() -> None:
    safety = active_safety()

    class StopAfterThreePlatform(FakePlatform):
        def wait_next(self, before: PageSnapshot, current_safety: SafetyController) -> None:
            super().wait_next(before, current_safety)
            if self.actions.count("submit") == 3:
                current_safety.stop()

    platform = StopAfterThreePlatform()
    records = asyncio.run(
        AutomationSession(
            make_task(), SequenceProvider([parsed_result()] * 3), platform, safety,
            AutomationSettings(observation_delay=0),
        ).run_many(None)
    )
    assert sum(record.submitted for record in records) == 3
    assert records[-1].state == RunState.STOPPED


def test_one_hundred_papers_run_serially_without_drift() -> None:
    platform = FakePlatform()
    records = asyncio.run(
        AutomationSession(
            make_task(), SequenceProvider([parsed_result()] * 100), platform,
            active_safety(), AutomationSettings(observation_delay=0),
        ).run_many(100)
    )
    assert len(records) == 100
    assert all(record.submitted and record.state == RunState.WAIT_NEXT for record in records)
    assert platform.actions.count("capture") == 100
    assert platform.actions.count("submit") == 100


def test_batch_stops_at_first_api_error_without_touching_next_paper() -> None:
    platform = FakePlatform()
    provider = SequenceProvider([
        ProviderError("one"), ProviderError("two"), ProviderError("three"), parsed_result()
    ])
    records = asyncio.run(
        AutomationSession(
            make_task(), provider, platform, active_safety(),
            AutomationSettings(observation_delay=0), sleeper=lambda _seconds: None,
        ).run_many(100)
    )
    assert len(records) == 1
    assert records[0].state == RunState.API_ERROR
    assert platform.actions.count("capture") == 1
    assert platform.actions.count("submit") == 0
