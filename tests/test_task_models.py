import json
from pathlib import Path

import pytest

from app.core.task_manager import load_task
from app.data.models import TaskValidationError


def test_example_task_loads() -> None:
    task = load_task(Path("examples/task.example.json"))
    assert task.max_score == 2
    assert len(task.rubric.items) == 2


def test_rubric_total_must_equal_task_total(tmp_path: Path) -> None:
    payload = json.loads(Path("examples/task.example.json").read_text(encoding="utf-8"))
    payload["max_score"] = 7
    path = tmp_path / "task.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(TaskValidationError, match="不一致"):
        load_task(path)


def test_unknown_task_field_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(Path("examples/task.example.json").read_text(encoding="utf-8"))
    payload["surprise"] = True
    path = tmp_path / "task.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(TaskValidationError, match="字段错误"):
        load_task(path)
