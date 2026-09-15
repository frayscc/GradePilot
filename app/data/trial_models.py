from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ErrorCategory(str, Enum):
    RECOGNITION = "recognition_error"
    RUBRIC = "rubric_error"
    PHYSICS_REASONING = "physics_reasoning_error"
    OTHER = "other"


class ReviewOutcome(str, Enum):
    UNREVIEWED = "unreviewed"
    AI_CORRECT = "ai_correct"
    AI_ERROR = "ai_error"


@dataclass(frozen=True)
class TrialSession:
    session_id: str
    task_id: str
    target_count: int
    error_threshold_percent: Decimal
    started_at: str


@dataclass(frozen=True)
class TrialRecord:
    record_id: str
    session_id: str
    sequence: int
    need_review: bool
    submitted: bool
    ai_score: Decimal
    correct_score: Decimal | None
    outcome: ReviewOutcome
    error_category: ErrorCategory | None
    note: str
    screenshot_path: str | None


@dataclass(frozen=True)
class TrialMetrics:
    target_count: int
    error_threshold_percent: Decimal
    processed: int
    ai_direct_normal: int
    automatic_submissions: int
    ai_requested_review: int
    review_ai_correct: int
    ai_actual_errors: int
    unreported_misjudgments: int

    @property
    def automatic_decisions(self) -> int:
        return self.automatic_submissions

    @property
    def unreported_rate_percent(self) -> Decimal:
        if not self.automatic_decisions:
            return Decimal("0")
        return Decimal(self.unreported_misjudgments) * Decimal("100") / Decimal(self.automatic_decisions)

    @property
    def actual_error_rate_percent(self) -> Decimal:
        if not self.processed:
            return Decimal("0")
        return Decimal(self.ai_actual_errors) * Decimal("100") / Decimal(self.processed)

    @property
    def meets_reference_condition(self) -> bool:
        return self.processed >= self.target_count and self.actual_error_rate_percent <= self.error_threshold_percent
