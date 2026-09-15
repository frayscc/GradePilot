import json

from app.data.models import Task

from .schemas import GRADE_RESULT_JSON_SCHEMA


SYSTEM_PROMPT = """你是中国初中物理阅卷助手。只返回一个 JSON 对象，不要 Markdown，不展示隐藏思维链。
必须根据完整物理语义评分，不能只匹配关键词。教师明确配置的接受或拒绝表达拥有最高优先级。
错别字默认在不改变物理含义时可给分，除非本空禁止错别字。单位、完全匹配规则按每空配置执行。
同一空同时保留相互矛盾的答案时直接给 0 分并说明，不要触发复核。
涂改后最终答案不明确、字迹存在会影响得分的多种解释时，need_review=true，并说明具体位置与原因。
数值答案不得自行换算成教师没有明确允许的其他形式。不得猜测。"""


def build_grading_prompt(task: Task) -> str:
    rubric = []
    for item in task.rubric.items:
        rubric.append(
            {
                "part": item.part,
                "max_score": float(item.max_score),
                "reference_answers": list(item.reference_answers),
                "criteria": item.criteria,
                "accepted_expressions": list(item.accepted_expressions),
                "rejected_expressions": list(item.rejected_expressions),
                "require_unit": item.require_unit,
                "exact_match": item.exact_match,
                "forbid_typos": item.forbid_typos,
                "notes": item.notes,
            }
        )
    context = {
        "task_name": task.name,
        "question_number": task.question_number,
        "question_text": task.question.text,
        "max_score": float(task.max_score),
        "score_step": float(task.score_step),
        "rule_version": task.rule_version,
        "rubric": rubric,
        "supplemental_rules": task.rubric.supplemental_rules,
    }
    return (
        "下面最后一张图片是学生答案区域；若还提供了题目图片，它位于学生答案图片之前。"
        "请将每个评分项都识别并评分，即使答案为空也要返回对应 part。\n"
        f"任务配置：{json.dumps(context, ensure_ascii=False)}\n"
        f"输出 JSON Schema：{json.dumps(GRADE_RESULT_JSON_SCHEMA, ensure_ascii=False)}"
    )
