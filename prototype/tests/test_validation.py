from decimal import Decimal

import pytest

from prototype.aigrader_proto.models import ValidationError, parse_grade_result


def valid_payload() -> dict:
    return {
        "recognized_answers": [{"part": "1", "text": "钩码数量"}],
        "grading": [{"part": "1", "score": 1, "max_score": 1, "reason": "语义正确"}],
        "total_score": 1,
        "max_score": 1,
        "need_review": False,
        "review_reason": None,
        "summary": "满分",
    }


def test_valid_result_is_parsed() -> None:
    result = parse_grade_result(valid_payload(), expected_max=Decimal("1"), score_step=Decimal("1"))
    assert result.total_score == Decimal("1")
    assert result.need_review is False


@pytest.mark.parametrize("score", [-1, 1.5, 3])
def test_illegal_total_is_rejected(score: float) -> None:
    payload = valid_payload()
    payload["total_score"] = score
    with pytest.raises(ValidationError):
        parse_grade_result(payload, expected_max=Decimal("1"), score_step=Decimal("1"))


def test_review_requires_reason() -> None:
    payload = valid_payload()
    payload["need_review"] = True
    with pytest.raises(ValidationError, match="review_reason"):
        parse_grade_result(payload, expected_max=Decimal("1"), score_step=Decimal("1"))


def test_unknown_fields_are_rejected() -> None:
    payload = valid_payload()
    payload["confidence"] = 0.99
    with pytest.raises(ValidationError, match="keys invalid"):
        parse_grade_result(payload, expected_max=Decimal("1"), score_step=Decimal("1"))
