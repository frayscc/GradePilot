from app.ai.prompts import build_grading_prompt

from .helpers import make_task


def test_prompt_contains_all_rubric_parts_and_schema() -> None:
    prompt = build_grading_prompt(make_task())
    assert '"part": "1"' in prompt
    assert '"part": "2"' in prompt
    assert "additionalProperties" in prompt
    assert "学生答案区域" in prompt
