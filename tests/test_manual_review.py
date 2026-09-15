from dataclasses import replace
from decimal import Decimal

from app.core.manual_review import ManualReviewSubmitter
from app.core.safety import RunState

from .helpers import make_task
from .test_automation_session import FakePlatform, active_safety, parsed_result


def test_human_can_submit_need_review_score_and_advance() -> None:
    platform = FakePlatform()
    result = replace(parsed_result(), need_review=True, review_reason="字迹不清")
    outcome = ManualReviewSubmitter(make_task(), platform, active_safety()).submit(
        result, Decimal("1"), platform.snapshot
    )
    assert outcome.submitted
    assert outcome.state == RunState.WAIT_NEXT
    assert platform.actions == [
        "assert_same", "enter", "snapshot", "submit", "wait_next"
    ]


def test_invalid_human_score_never_touches_page() -> None:
    platform = FakePlatform()
    result = replace(parsed_result(), need_review=True, review_reason="字迹不清")
    outcome = ManualReviewSubmitter(make_task(), platform, active_safety()).submit(
        result, Decimal("1.5"), platform.snapshot
    )
    assert not outcome.submitted
    assert outcome.state == RunState.VALIDATION_ERROR
    assert platform.actions == []
