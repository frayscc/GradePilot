from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.ai.schemas import GradeResult
from app.core.safety import AutomationBlocked, RunState, SafetyController, SubmissionPermit
from app.data.models import Task
from app.platforms.base import GradingPlatform, PageSnapshot, PageTransitionError


@dataclass(frozen=True)
class ManualSubmissionResult:
    submitted: bool
    state: RunState
    error: str | None = None
    submit_clicked: bool = False


class ManualReviewSubmitter:
    def __init__(
        self, task: Task, platform: GradingPlatform, safety: SafetyController
    ) -> None:
        self.task = task
        self.platform = platform
        self.safety = safety

    def submit(
        self, result: GradeResult, score: Decimal, expected_page: PageSnapshot
    ) -> ManualSubmissionResult:
        if score < 0 or score > self.task.max_score or score % self.task.score_step != 0:
            return ManualSubmissionResult(
                False, RunState.VALIDATION_ERROR,
                f"人工分数必须在 0～{self.task.max_score} 且符合步长 {self.task.score_step}",
            )
        permit = SubmissionPermit(
            result,
            manual_review_authorized=True,
            override_score=score,
        )
        submission_clicked = False
        try:
            self.platform.assert_same_answer(expected_page)
            self.safety.guard(permit)
            self.platform.enter_score(permit)
            self.safety.guard(permit)
            before_submit = self.platform.snapshot_page()
            self.platform.submit(permit)
            submission_clicked = True
            self.platform.wait_next(before_submit, self.safety)
            return ManualSubmissionResult(True, RunState.WAIT_NEXT, submit_clicked=True)
        except PageTransitionError as exc:
            self.safety.stop()
            prefix = "人工提交点击已执行，但下一页未确认" if submission_clicked else "人工提交前页面异常"
            return ManualSubmissionResult(
                False, RunState.PAGE_ERROR, f"{prefix}：{exc}", submission_clicked
            )
        except AutomationBlocked as exc:
            return ManualSubmissionResult(
                False, RunState.STOPPED if self.safety.stopped else RunState.PAUSED,
                str(exc), submission_clicked,
            )
        except Exception as exc:
            self.safety.stop()
            return ManualSubmissionResult(False, RunState.STOPPED, str(exc), submission_clicked)
