from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from app.data.models import Task, TaskValidationError


SUPPORTED_QUESTION_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def grading_signature(task: Task) -> tuple:
    return task.max_score, task.score_step, task.question, task.rubric


def ensure_rule_version(original: Task | None, updated: Task) -> Task:
    """Increment the version when grading inputs changed and the user did not."""
    if original is None or grading_signature(original) == grading_signature(updated):
        return updated
    return replace(updated, rule_version=max(updated.rule_version, original.rule_version + 1))


def load_task(path: Path) -> Task:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskValidationError(f"任务文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise TaskValidationError(f"任务文件不是有效 JSON：{exc}") from exc
    return Task.from_dict(payload, base_dir=path.parent)


def save_task(task: Task, path: Path) -> None:
    """Atomically replace a task file, leaving the last valid copy intact on failure."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(task.to_dict(base_dir=path.parent), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def store_question_image(source: Path, task_path: Path) -> Path:
    source = source.resolve()
    if not source.is_file():
        raise TaskValidationError(f"题目图片不存在：{source}")
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_QUESTION_IMAGES:
        raise TaskValidationError(f"不支持的题图格式：{suffix}")
    asset_dir = task_path.resolve().parent / f"{task_path.stem}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    destination = asset_dir / f"question{suffix}"
    if source == destination:
        return destination
    temporary: Path | None = None
    try:
        with source.open("rb") as input_file, tempfile.NamedTemporaryFile(
            mode="wb", dir=asset_dir, prefix=".question.", suffix=".tmp", delete=False
        ) as output_file:
            temporary = Path(output_file.name)
            shutil.copyfileobj(input_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination
