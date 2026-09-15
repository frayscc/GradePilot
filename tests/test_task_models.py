import json
from pathlib import Path

import pytest

from app.core.task_manager import load_task
from app.data.models import TaskValidationError


def test_example_task_loads() -> None:
    task = load_task(Path("examples/task.example.json"))
    assert task.max_score == 2
    assert len(task.rubric.items) == 2
    assert task.observation_delay == 1.0
    assert task.max_continuous == 100
    assert task.pause_hotkey == "f8"


def test_legacy_task_without_automation_settings_uses_safe_defaults(tmp_path: Path) -> None:
    payload = json.loads(Path("examples/task.example.json").read_text(encoding="utf-8"))
    payload.pop("automation")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    task = load_task(path)
    assert task.observation_delay == 1.0
    assert task.max_continuous == 100
    assert (task.pause_hotkey, task.resume_hotkey, task.stop_hotkey) == (
        "f8", "f9", "ctrl+alt+q"
    )


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
