from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.ai.base import AIProvider, ProviderError
from app.ai.schemas import GradeRequest, GradeResult, ResultValidationError
from app.data.models import Task
from app.platforms.base import GradingPlatform, PageTransitionError

from .safety import AutomationBlocked, RunState, SafetyController, SubmissionPermit


@dataclass(frozen=True)
class AutomationSettings:
    observation_delay: float = 1.0
    retry_delays: tuple[float, float] = (2.0, 5.0)

    def __post_init__(self) -> None:
        if not 0 <= self.observation_delay <= 5:
            raise ValueError("提交前观察时间必须在 0～5 秒之间")


@dataclass(frozen=True)
class AutomationRunResult:
    index: int
    state: RunState
    result: GradeResult | None
    submitted: bool
    error: str | None


class AutomationSession:
    def __init__(
        self,
        task: Task,
        provider: AIProvider,
        platform: GradingPlatform,
        safety: SafetyController,
        settings: AutomationSettings = AutomationSettings(),
        *,
        on_state: Callable[[RunState, str], None] | None = None,
        on_result: Callable[[GradeResult], None] | None = None,
        on_result_detail: Callable[[int, GradeResult, Path], None] | None = None,
        on_completed: Callable[[AutomationRunResult, Path], None] | None = None,
        capture_directory: Path | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.task = task
        self.provider = provider
        self.platform = platform
        self.safety = safety
        self.settings = settings
        self.on_state = on_state or (lambda _state, _message: None)
        self.on_result = on_result or (lambda _result: None)
        self.on_result_detail = on_result_detail or (lambda _index, _result, _image: None)
        self.on_completed = on_completed or (lambda _record, _image: None)
        self.capture_directory = capture_directory
        self.sleeper = sleeper
        self.clock = clock

    def emit(self, state: RunState, message: str) -> None:
        self.on_state(state, message)

    def interruptible_wait(self, seconds: float) -> None:
        deadline = self.clock() + seconds
        while self.clock() < deadline:
            if self.safety.stopped:
                raise AutomationBlocked("自动化已紧急停止")
            if self.safety.paused:
                raise AutomationBlocked("自动化已暂停，本份不会提交")
            self.sleeper(min(0.05, max(0, deadline - self.clock())))

    async def request_with_retry(self, image: Path) -> GradeResult:
        last_error: ProviderError | None = None
        for attempt in range(3):
            self.emit(RunState.AI_REQUEST, f"请求 AI（第 {attempt + 1}/3 次）")
            try:
                result = await self.provider.grade(GradeRequest(self.task, image))
                self.emit(RunState.AI_VALIDATION, "AI JSON 与分数验证通过")
                return result
            except ProviderError as exc:
                last_error = exc
                if attempt == 2:
                    break
                self.interruptible_wait(self.settings.retry_delays[attempt])
        assert last_error is not None
        raise last_error

    async def run_one(self, index: int) -> AutomationRunResult:
        if self.capture_directory is not None:
            self.capture_directory.mkdir(parents=True, exist_ok=True)
            image = self.capture_directory / f"answer-{index:04}.png"
            record = await self._run_one_with_image(index, image)
            if record.state != RunState.PAUSED:
                self.on_completed(record, image)
            return record
        with tempfile.TemporaryDirectory(prefix="aigrader-") as directory:
            image = Path(directory) / "answer.png"
            record = await self._run_one_with_image(index, image)
            if record.state != RunState.PAUSED:
                self.on_completed(record, image)
            return record

    async def _run_one_with_image(self, index: int, image: Path) -> AutomationRunResult:
        result: GradeResult | None = None
        submission_clicked = False
        try:
            if not self.safety.enabled or self.safety.stopped or self.safety.paused:
                raise AutomationBlocked("自动化尚未处于可运行状态")
            self.emit(RunState.CAPTURE, f"截取第 {index} 份学生答案")
            initial_page = self.platform.snapshot_page()
            self.platform.capture_answer(image)
            result = await self.request_with_retry(image)
            self.on_result(result)
            self.on_result_detail(index, result, image)
            if result.need_review:
                self.safety.pause()
                self.emit(RunState.NEED_REVIEW, result.review_reason or "AI 要求人工复核")
                return AutomationRunResult(index, RunState.NEED_REVIEW, result, False, result.review_reason)
            self.emit(RunState.SHOW_RESULT, f"AI 得分 {result.total_score}/{result.max_score}")
            permit = SubmissionPermit(result)
            self.emit(RunState.OBSERVATION_DELAY, f"观察 {self.settings.observation_delay:.1f} 秒")
            self.interruptible_wait(self.settings.observation_delay)
            self.safety.guard(permit)
            self.platform.assert_same_answer(initial_page)
            self.emit(RunState.ENTER_SCORE, f"填写分数 {result.total_score}")
            self.platform.enter_score(permit)
            self.safety.guard(permit)
            before_submit = self.platform.snapshot_page()
            self.emit(RunState.SUBMIT, "提交前最终安全检查通过")
            self.platform.submit(permit)
            submission_clicked = True
            self.emit(RunState.WAIT_NEXT, "等待下一份页面")
            self.platform.wait_next(before_submit, self.safety)
            return AutomationRunResult(index, RunState.WAIT_NEXT, result, True, None)
        except ResultValidationError as exc:
            self.safety.pause()
            self.emit(RunState.VALIDATION_ERROR, str(exc))
            return AutomationRunResult(index, RunState.VALIDATION_ERROR, result, False, str(exc))
        except ProviderError as exc:
            self.safety.pause()
            self.emit(RunState.API_ERROR, str(exc))
            return AutomationRunResult(index, RunState.API_ERROR, result, False, str(exc))
        except PageTransitionError as exc:
            self.safety.pause()
            message = f"提交点击已执行，但下一页未确认：{exc}" if submission_clicked else str(exc)
            self.emit(RunState.PAGE_ERROR, message)
            return AutomationRunResult(index, RunState.PAGE_ERROR, result, False, message)
        except AutomationBlocked as exc:
            if submission_clicked:
                self.safety.stop()
                message = f"提交点击已执行，但等待下一页时中止：{exc}。已停止，禁止自动重试本份"
                self.emit(RunState.PAGE_ERROR, message)
                return AutomationRunResult(index, RunState.PAGE_ERROR, result, False, message)
            state = RunState.STOPPED if self.safety.stopped else RunState.PAUSED
            self.emit(state, str(exc))
            return AutomationRunResult(index, state, result, False, str(exc))
        except Exception as exc:
            self.safety.stop()
            self.emit(RunState.STOPPED, f"未预期异常：{exc}")
            return AutomationRunResult(index, RunState.STOPPED, result, False, str(exc))

    async def run_many(self, count: int, *, start_index: int = 1) -> list[AutomationRunResult]:
        if count < 1:
            raise ValueError("处理份数至少为 1")
        if start_index < 1:
            raise ValueError("起始序号至少为 1")
        records: list[AutomationRunResult] = []
        for index in range(start_index, start_index + count):
            while True:
                record = await self.run_one(index)
                if record.state != RunState.PAUSED:
                    records.append(record)
                    break
                self.emit(RunState.PAUSED, "已暂停；按 F9 或点击继续后将从本份重新截图评分")
                while self.safety.paused and not self.safety.stopped:
                    self.sleeper(0.1)
                if self.safety.stopped:
                    record = AutomationRunResult(index, RunState.STOPPED, record.result, False, "自动化已紧急停止")
                    records.append(record)
                    break
            if records[-1].state != RunState.WAIT_NEXT or not records[-1].submitted:
                break
        return records
