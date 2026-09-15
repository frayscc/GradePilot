from decimal import Decimal

from app.data.models import Question, Rubric, RubricItem, Task


def make_task() -> Task:
    return Task(
        task_id="task-16",
        name="物理测试",
        question_number="16",
        max_score=Decimal("2"),
        score_step=Decimal("1"),
        provider="deepseek",
        model="deepseek-flash",
        rule_version=1,
        question=Question("填写实验结论"),
        rubric=Rubric(
            (
                RubricItem("1", Decimal("1"), ("定",), "与参考答案语义一致"),
                RubricItem("2", Decimal("1"), ("不能",), "与参考答案语义一致"),
            ),
            "按最终保留答案评分",
        ),
    )


def valid_result() -> dict:
    return {
        "recognized_answers": [{"part": "1", "text": "定"}, {"part": "2", "text": "不能"}],
        "grading": [
            {"part": "1", "score": 1, "max_score": 1, "reason": "一致"},
            {"part": "2", "score": 1, "max_score": 1, "reason": "一致"},
        ],
        "total_score": 2,
        "max_score": 2,
        "need_review": False,
        "review_reason": None,
        "summary": "全部正确",
    }
