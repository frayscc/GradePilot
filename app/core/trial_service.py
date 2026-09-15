from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from app.ai.schemas import GradeResult
from app.core.automation_session import AutomationRunResult
from app.data.models import Task
from app.data.repository import TrialRepository
from app.data.trial_models import ErrorCategory, TrialMetrics, TrialRecord, TrialSession


class TrialService:
    def __init__(self, repository: TrialRepository, session: TrialSession, task: Task) -> None:
        self.repository = repository
        self.session = session
        self.task = task

    @classmethod
    def start(
        cls,
        repository: TrialRepository,
        task: Task,
        *,
        target_count: int = 100,
        error_threshold_percent: Decimal = Decimal("5"),
    ) -> "TrialService":
        return cls(
            repository,
            repository.create_session(
                task, target_count=target_count, error_threshold_percent=error_threshold_percent
            ),
            task,
        )

    def record_ai_result(
        self,
        sequence: int,
        result: GradeResult,
        screenshot: Path,
        *,
        automation_state: str,
    ) -> TrialRecord:
        record = self.repository.add_result(
            self.session, sequence, self.task, result, automation_state=automation_state
        )
        if result.need_review:
            self.repository.archive_screenshot(record.record_id, screenshot)
            record = self.repository.get_record(record.record_id)
        return record

    def complete_automation(self, record_id: str, result: AutomationRunResult) -> None:
        self.repository.update_automation(
            record_id, submitted=result.submitted, automation_state=result.state.value
        )

    def mark_ai_correct(self, record_id: str, correct_score: Decimal) -> None:
        self._validate_score(correct_score)
        self.repository.mark_ai_correct(record_id, correct_score=correct_score)

    def mark_ai_error(
        self,
        record_id: str,
        screenshot: Path,
        correct_score: Decimal,
        category: ErrorCategory,
        note: str = "",
    ) -> None:
        self._validate_score(correct_score)
        self.repository.archive_screenshot(record_id, screenshot)
        self.repository.mark_ai_error(
            record_id, correct_score=correct_score, category=category, note=note
        )

    def _validate_score(self, score: Decimal) -> None:
        if score < 0 or score > self.task.max_score or score % self.task.score_step != 0:
            raise ValueError(f"正确分数必须在 0～{self.task.max_score} 且符合步长 {self.task.score_step}")

    def metrics(self) -> TrialMetrics:
        return self.repository.metrics(self.session.session_id)

    def report(self) -> dict:
        metrics = self.metrics()
        return {
            "session_id": self.session.session_id,
            "task_id": self.session.task_id,
            "started_at": self.session.started_at,
            "target_count": metrics.target_count,
            "processed": metrics.processed,
            "ai_direct_normal": metrics.ai_direct_normal,
            "ai_requested_review": metrics.ai_requested_review,
            "review_ai_correct": metrics.review_ai_correct,
            "ai_actual_errors": metrics.ai_actual_errors,
            "error_categories": self.repository.error_category_counts(self.session.session_id),
            "automatic_submissions": metrics.automatic_submissions,
            "unreported_misjudgments": metrics.unreported_misjudgments,
            "unreported_rate_percent": float(metrics.unreported_rate_percent),
            "actual_error_rate_percent": float(metrics.actual_error_rate_percent),
            "error_threshold_percent": float(metrics.error_threshold_percent),
            "meets_automatic_mode_reference": metrics.meets_reference_condition,
            "automatic_mode_enabled": False,
        }

    def export_report(self, destination: Path) -> Path:
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self.report(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
