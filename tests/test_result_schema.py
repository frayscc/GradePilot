from copy import deepcopy

import pytest

from app.ai.schemas import ResultValidationError, validate_grade_result

from .helpers import make_task, valid_result


def test_complete_result_validates() -> None:
    result = validate_grade_result(valid_result(), make_task())
    assert result.total_score == 2


def test_missing_part_is_rejected() -> None:
    payload = deepcopy(valid_result())
    payload["recognized_answers"].pop()
    with pytest.raises(ResultValidationError, match="完全一致"):
        validate_grade_result(payload, make_task())


def test_wrong_part_max_is_rejected() -> None:
    payload = deepcopy(valid_result())
    payload["grading"][0]["max_score"] = 2
    with pytest.raises(ResultValidationError, match="满分无效"):
        validate_grade_result(payload, make_task())


def test_non_review_result_requires_null_reason() -> None:
    payload = deepcopy(valid_result())
    payload["review_reason"] = "也许"
    with pytest.raises(ResultValidationError, match="必须为 null"):
        validate_grade_result(payload, make_task())
