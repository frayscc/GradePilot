import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.schemas import validate_grade_result
from app.core.trial_service import TrialService
from app.data.repository import TrialRepository
from app.data.trial_models import ErrorCategory

from .helpers import make_task, valid_result


def setup_trial(tmp_path: Path, *, target: int = 3, threshold: str = "5") -> tuple[TrialRepository, TrialService]:
    repository = TrialRepository(tmp_path / "trials.db", tmp_path / "archive")
    service = TrialService.start(
        repository, make_task(), target_count=target, error_threshold_percent=Decimal(threshold)
    )
    return repository, service


def add_record(service: TrialService, tmp_path: Path, sequence: int, *, review: bool = False):
    screenshot = tmp_path / f"answer-{sequence}.png"
    screenshot.write_bytes(b"student-answer")
    result = validate_grade_result(valid_result(), make_task())
    if review:
        result = replace(result, need_review=True, review_reason="字迹不清")
    return service.record_ai_result(sequence, result, screenshot, automation_state="SHOW_RESULT"), screenshot


def test_trial_metrics_distinguish_review_and_unreported_error(tmp_path: Path) -> None:
    repository, service = setup_trial(tmp_path, target=3, threshold="40")
    first, first_image = add_record(service, tmp_path, 1)
    second, _ = add_record(service, tmp_path, 2, review=True)
    third, _ = add_record(service, tmp_path, 3)
    repository.update_automation(first.record_id, submitted=True, automation_state="WAIT_NEXT")
    repository.update_automation(third.record_id, submitted=True, automation_state="WAIT_NEXT")
    service.mark_ai_error(first.record_id, first_image, Decimal("1"), ErrorCategory.RECOGNITION, "看错字")
    service.mark_ai_correct(second.record_id, Decimal("2"))
    metrics = service.metrics()
    assert metrics.processed == 3
    assert metrics.ai_direct_normal == 1
    assert metrics.automatic_decisions == 2
    assert metrics.ai_requested_review == 1
    assert metrics.review_ai_correct == 1
    assert metrics.ai_actual_errors == 1
    assert metrics.unreported_misjudgments == 1
    assert metrics.unreported_rate_percent == Decimal("50")
    assert metrics.meets_reference_condition


def test_need_review_screenshot_is_archived_automatically(tmp_path: Path) -> None:
    repository, service = setup_trial(tmp_path)
    record, _ = add_record(service, tmp_path, 1, review=True)
    saved = repository.get_record(record.record_id)
    assert saved.screenshot_path is not None
    assert Path(saved.screenshot_path).read_bytes() == b"student-answer"


def test_error_archive_contains_task_and_structured_result(tmp_path: Path) -> None:
    repository, service = setup_trial(tmp_path)
    record, screenshot = add_record(service, tmp_path, 1)
    service.mark_ai_error(record.record_id, screenshot, Decimal("1"), ErrorCategory.RUBRIC, "规则理解错误")
    saved = repository.get_record(record.record_id)
    assert saved.error_category == ErrorCategory.RUBRIC
    assert saved.correct_score == Decimal("1")
    assert Path(saved.screenshot_path).is_file()
    with repository.connect() as connection:
        raw = connection.execute(
            "SELECT task_snapshot, result_json, model, created_at FROM trial_records WHERE record_id = ?",
            (record.record_id,),
        ).fetchone()
    assert "物理测试" in raw["task_snapshot"]
    assert "recognized_answers" in raw["result_json"]
    assert raw["model"] == "deepseek-flash"
    assert raw["created_at"]


def test_correct_score_must_follow_task_step(tmp_path: Path) -> None:
    _, service = setup_trial(tmp_path)
    record, screenshot = add_record(service, tmp_path, 1)
    with pytest.raises(ValueError, match="步长"):
        service.mark_ai_error(record.record_id, screenshot, Decimal("1.5"), ErrorCategory.OTHER)


def test_one_hundred_paper_trial_report(tmp_path: Path) -> None:
    repository, service = setup_trial(tmp_path, target=100, threshold="15")
    categories = list(ErrorCategory)
    for sequence in range(1, 101):
        needs_review = 71 <= sequence <= 90
        record, screenshot = add_record(service, tmp_path, sequence, review=needs_review)
        if not needs_review:
            repository.update_automation(
                record.record_id, submitted=True, automation_state="WAIT_NEXT"
            )
        if 71 <= sequence <= 85:
            service.mark_ai_correct(record.record_id, Decimal("2"))
        elif 86 <= sequence <= 100:
            service.mark_ai_error(
                record.record_id,
                screenshot,
                Decimal("1"),
                categories[(sequence - 86) % len(categories)],
                "100 份模拟验收",
            )

    metrics = service.metrics()
    assert metrics.processed == 100
    assert metrics.ai_direct_normal == 70
    assert metrics.ai_requested_review == 20
    assert metrics.review_ai_correct == 15
    assert metrics.ai_actual_errors == 15
    assert metrics.automatic_submissions == 80
    assert metrics.unreported_misjudgments == 10
    assert metrics.unreported_rate_percent == Decimal("12.5")
    assert metrics.meets_reference_condition

    destination = service.export_report(tmp_path / "reports" / "trial-report.json")
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert report["processed"] == 100
    assert report["ai_direct_normal"] == 70
    assert report["ai_requested_review"] == 20
    assert report["ai_actual_errors"] == 15
    assert report["unreported_rate_percent"] == 12.5
    assert report["meets_automatic_mode_reference"] is True
    assert report["automatic_mode_enabled"] is False
    assert sum(report["error_categories"].values()) == 15
    qualified = repository.latest_qualifying_session(make_task().task_id)
    assert qualified is not None
    assert qualified.session_id == service.session.session_id


def test_unresolved_review_cannot_unlock_automatic_mode(tmp_path: Path) -> None:
    repository, service = setup_trial(tmp_path, target=1, threshold="100")
    add_record(service, tmp_path, 1, review=True)
    assert service.metrics().meets_reference_condition
    assert repository.latest_qualifying_session(make_task().task_id) is None
