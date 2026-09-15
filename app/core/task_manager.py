import json
from pathlib import Path

from app.data.models import Task, TaskValidationError


def load_task(path: Path) -> Task:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskValidationError(f"任务文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise TaskValidationError(f"任务文件不是有效 JSON：{exc}") from exc
    return Task.from_dict(payload, base_dir=path.parent)
