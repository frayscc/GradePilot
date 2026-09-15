import json
from pathlib import Path

import pytest

import app.core.task_manager as task_manager
from app.core.task_manager import load_task, save_task, store_question_image

from .helpers import make_task


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "tasks" / "task.json"
    task = make_task()
    save_task(task, path)
    loaded = load_task(path)
    assert loaded == task
    assert list(path.parent.glob("*.tmp")) == []


def test_question_image_inside_task_directory_is_saved_relative(tmp_path: Path) -> None:
    image = tmp_path / "question.png"
    image.write_bytes(b"png")
    task = make_task()
    from app.data.models import Question, Task

    task_with_image = Task(
        task.task_id,
        task.name,
        task.question_number,
        task.max_score,
        task.score_step,
        task.provider,
        task.model,
        task.rule_version,
        Question(task.question.text, image),
        task.rubric,
    )
    path = tmp_path / "task.json"
    save_task(task_with_image, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["question"]["image_path"] == "question.png"
    assert load_task(path) == task_with_image


def test_selected_question_image_is_copied_next_to_task(tmp_path: Path) -> None:
    source_dir = tmp_path / "downloads"
    source_dir.mkdir()
    source = source_dir / "photo.PNG"
    source.write_bytes(b"question-image")
    task_path = tmp_path / "tasks" / "physics.json"
    stored = store_question_image(source, task_path)
    assert stored == tmp_path / "tasks" / "physics_assets" / "question.png"
    assert stored.read_bytes() == b"question-image"
    assert list(stored.parent.glob("*.tmp")) == []


def test_failed_atomic_replace_keeps_previous_task_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "task.json"
    path.write_text("previous-valid-content", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr(task_manager.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        save_task(make_task(), path)
    assert path.read_text(encoding="utf-8") == "previous-valid-content"
    assert list(tmp_path.glob("*.tmp")) == []
