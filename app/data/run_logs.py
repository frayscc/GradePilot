from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path

from app.core.automation_session import AutomationRunResult
from app.core.safety import RunState
from app.data.models import Task


class RunLogRepository:
    """Persistent per-paper logs shared by trial and automatic modes."""

    def __init__(self, database_path: Path, exception_archive_dir: Path) -> None:
        self.database_path = database_path.resolve()
        self.exception_archive_dir = exception_archive_dir.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.exception_archive_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS grading_logs (
                    log_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    paper_index INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    latency_ms INTEGER,
                    result_json TEXT,
                    need_review INTEGER NOT NULL CHECK(need_review IN (0, 1)),
                    api_success INTEGER NOT NULL CHECK(api_success IN (0, 1)),
                    score_entered INTEGER NOT NULL CHECK(score_entered IN (0, 1)),
                    submit_clicked INTEGER NOT NULL CHECK(submit_clicked IN (0, 1)),
                    submitted INTEGER NOT NULL CHECK(submitted IN (0, 1)),
                    state TEXT NOT NULL,
                    error TEXT,
                    rule_version INTEGER NOT NULL,
                    task_snapshot TEXT NOT NULL,
                    screenshot_path TEXT,
                    review_outcome TEXT NOT NULL DEFAULT 'unreviewed',
                    correct_score TEXT,
                    error_category TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    manual_submitted INTEGER NOT NULL DEFAULT 0 CHECK(manual_submitted IN (0, 1))
                )"""
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(grading_logs)").fetchall()
            }
            migrations = {
                "review_outcome": "TEXT NOT NULL DEFAULT 'unreviewed'",
                "correct_score": "TEXT",
                "error_category": "TEXT",
                "note": "TEXT NOT NULL DEFAULT ''",
                "manual_submitted": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE grading_logs ADD COLUMN {name} {definition}")

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, task: Task, record: AutomationRunResult, mode: str, screenshot: Path) -> str:
        log_id = str(uuid.uuid4())
        screenshot_path: str | None = None
        if record.state != RunState.WAIT_NEXT and screenshot.is_file():
            destination = self.exception_archive_dir / f"{log_id}{screenshot.suffix.lower() or '.png'}"
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            try:
                shutil.copy2(screenshot, temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            screenshot_path = str(destination)
        result_json = json.dumps(record.result.as_dict(), ensure_ascii=False) if record.result else None
        try:
            with self.connect() as connection:
                connection.execute(
                    """INSERT INTO grading_logs (
                        log_id, mode, task_id, paper_index, started_at, completed_at,
                        provider, model, latency_ms, result_json, need_review, api_success,
                        score_entered, submit_clicked, submitted, state, error, rule_version,
                        task_snapshot, screenshot_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        log_id, mode, task.task_id, record.index, record.started_at,
                        record.completed_at, task.provider, task.model, record.latency_ms,
                        result_json, int(bool(record.result and record.result.need_review)),
                        int(record.api_success), int(record.score_entered), int(record.submit_clicked),
                        int(record.submitted), record.state.value, record.error, task.rule_version,
                        json.dumps(task.to_dict(), ensure_ascii=False), screenshot_path,
                    ),
                )
        except Exception:
            if screenshot_path:
                Path(screenshot_path).unlink(missing_ok=True)
            raise
        return log_id

    def mark_review(
        self,
        log_id: str,
        *,
        correct_score: str,
        ai_correct: bool,
        error_category: str | None = None,
        note: str = "",
    ) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE grading_logs SET review_outcome = ?, correct_score = ?,
                error_category = ?, note = ? WHERE log_id = ?""",
                (
                    "ai_correct" if ai_correct else "ai_error", correct_score,
                    error_category, note.strip(), log_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"自动阅卷日志不存在：{log_id}")

    def update_manual_submission(self, log_id: str, *, submitted: bool, state: str, error: str | None) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE grading_logs SET manual_submitted = ?, submitted = ?, state = ?, error = ?
                WHERE log_id = ?""",
                (int(submitted), int(submitted), state, error, log_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"自动阅卷日志不存在：{log_id}")

    def get(self, log_id: str) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM grading_logs WHERE log_id = ?", (log_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"自动阅卷日志不存在：{log_id}")
        return row

    def records(self, task_id: str, *, mode: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM grading_logs WHERE task_id = ?"
        parameters: tuple[object, ...] = (task_id,)
        if mode is not None:
            query += " AND mode = ?"
            parameters += (mode,)
        query += " ORDER BY rowid"
        with self.connect() as connection:
            return connection.execute(query, parameters).fetchall()

    def next_index(self, task_id: str, *, mode: str = "automatic") -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(paper_index) AS maximum FROM grading_logs WHERE task_id = ? AND mode = ?",
                (task_id, mode),
            ).fetchone()
        return int(row["maximum"] or 0) + 1
