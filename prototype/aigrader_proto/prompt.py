import json

from .models import GradeRequest


SYSTEM_PROMPT = """你是中国初中物理阅卷助手。只输出一个 JSON 对象，不要 Markdown，不要隐藏思维链。
必须按完整语义评分，教师明确接受/拒绝的表达优先。无法可靠辨认且影响得分时 need_review=true。
同一空保留互相矛盾的答案时直接给 0 分并说明，不要因此要求复核。数值形式只按明确规则等价。
输出必须严格符合用户提供的字段结构；不得猜测缺失答案。"""


def build_prompt(request: GradeRequest) -> str:
    schema = {
        "recognized_answers": [{"part": "string", "text": "string"}],
        "grading": [{"part": "string", "score": "number", "max_score": "number", "reason": "string"}],
        "total_score": "number",
        "max_score": float(request.max_score),
        "need_review": "boolean",
        "review_reason": "string or null",
        "summary": "string",
    }
    return (
        f"题目：\n{request.question_text}\n\n"
        f"评分规则：\n{request.rubric_text}\n\n"
        f"整题满分：{request.max_score}；总分步长：{request.score_step}。\n"
        "请识别图片中的各空答案并评分。输出字段必须且只能是：\n"
        + json.dumps(schema, ensure_ascii=False)
    )
