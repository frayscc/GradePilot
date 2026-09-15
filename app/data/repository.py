from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.ai.schemas import GradeResult
from app.data.models import Task
from app.data.trial_models import ErrorCategory, ReviewOutcome, TrialMetrics, TrialRecord, TrialSession
from app.core.task_manager import grading_fingerprint


class TrialRepository:
    def __init__(self, database_path: Path, archive_dir: Path) -> None:
        self.database_path = database_path.resolve()
        self.archive_dir = archive_dir.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trial_sessions (
                    session_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    target_count INTEGER NOT NULL CHECK(target_count > 0),
                    error_threshold_percent TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    rule_version INTEGER NOT NULL DEFAULT 1,
                    grading_fingerprint TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS trial_records (
                    record_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES trial_sessions(session_id),
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task_snapshot TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    need_review INTEGER NOT NULL CHECK(need_review IN (0, 1)),
                    submitted INTEGER NOT NULL CHECK(submitted IN (0, 1)),
                    automation_state TEXT NOT NULL,
                    ai_score TEXT NOT NULL,
                    correct_score TEXT,
                    outcome TEXT NOT NULL,
                    error_category TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    screenshot_path TEXT,
                    UNIQUE(session_id, sequence)
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(trial_sessions)").fetchall()
            }
            if "rule_version" not in columns:
                connection.execute(
                    "ALTER TABLE trial_sessions ADD COLUMN rule_version INTEGER NOT NULL DEFAULT 1"
                )
            if "grading_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE trial_sessions ADD COLUMN grading_fingerprint TEXT NOT NULL DEFAULT ''"
                )

    def create_session(self, task: Task, *, target_count: int = 100, error_threshold_percent: Decimal = Decimal("5")) -> TrialSession:
        if target_count <= 0:
            raise ValueError("试改目标必须大于 0")
        if error_threshold_percent < 0 or error_threshold_percent > 100:
            raise ValueError("错判率阈值必须在 0～100% 之间")
        session = TrialSession(
            str(uuid.uuid4()), task.task_id, target_count, error_threshold_percent,
            datetime.now(timezone.utc).isoformat(), task.rule_version, grading_fingerprint(task),
        )
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO trial_sessions (
                    session_id, task_id, target_count, error_threshold_percent, started_at,
                    rule_version, grading_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.session_id, session.task_id, session.target_count,
                    str(session.error_threshold_percent), session.started_at,
                    session.rule_version, session.grading_fingerprint,
                ),
            )
        return session

    def add_result(self, session: TrialSession, sequence: int, task: Task, result: GradeResult, *, automation_state: str) -> TrialRecord:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT record_id FROM trial_records WHERE session_id = ? AND sequence = ?",
                (session.session_id, sequence),
            ).fetchone()
        record_id = existing["record_id"] if existing else str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            if existing:
                connection.execute(
                    """UPDATE trial_records SET
                        created_at = ?, model = ?, task_snapshot = ?, result_json = ?, need_review = ?,
                        submitted = 0, automation_state = ?, ai_score = ?, correct_score = NULL,
                        outcome = ?, error_category = NULL, note = '', screenshot_path = NULL
                    WHERE record_id = ?""",
                    (
                        created_at, task.model, json.dumps(task.to_dict(), ensure_ascii=False),
                        json.dumps(result.as_dict(), ensure_ascii=False), int(result.need_review),
                        automation_state, str(result.total_score), ReviewOutcome.UNREVIEWED.value, record_id,
                    ),
                )
            else:
                connection.execute(
                    """INSERT INTO trial_records (
                        record_id, session_id, sequence, created_at, model, task_snapshot, result_json,
                        need_review, submitted, automation_state, ai_score, correct_score, outcome,
                        error_category, note, screenshot_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, NULL, '', NULL)""",
                    (
                        record_id, session.session_id, sequence, created_at, task.model,
                        json.dumps(task.to_dict(), ensure_ascii=False),
                        json.dumps(result.as_dict(), ensure_ascii=False),
                        int(result.need_review), automation_state, str(result.total_score), ReviewOutcome.UNREVIEWED.value,
                    ),
                )
        return self.get_record(record_id)

    def get_record_for_sequence(self, session_id: str, sequence: int) -> TrialRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record_id FROM trial_records WHERE session_id = ? AND sequence = ?", (session_id, sequence)
            ).fetchone()
        if row is None:
            raise KeyError(f"试改记录不存在：{sequence}")
        return self.get_record(row["record_id"])

    def update_automation(self, record_id: str, *, submitted: bool, automation_state: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE trial_records SET submitted = ?, automation_state = ? WHERE record_id = ?",
                (int(submitted), automation_state, record_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"试改记录不存在：{record_id}")

    def archive_screenshot(self, record_id: str, source: Path) -> Path:
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = self.archive_dir / f"{record_id}{source.suffix.lower() or '.png'}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE trial_records SET screenshot_path = ? WHERE record_id = ?",
                (str(destination), record_id),
            )
            if cursor.rowcount != 1:
                destination.unlink(missing_ok=True)
                raise KeyError(f"试改记录不存在：{record_id}")
        return destination

    def mark_ai_correct(self, record_id: str, *, correct_score: Decimal) -> None:
        self._mark(record_id, ReviewOutcome.AI_CORRECT, correct_score, None, "")

    def mark_ai_error(
        self,
        record_id: str,
        *,
        correct_score: Decimal,
        category: ErrorCategory,
        note: str = "",
    ) -> None:
        self._mark(record_id, ReviewOutcome.AI_ERROR, correct_score, category, note)

    def _mark(
        self,
        record_id: str,
        outcome: ReviewOutcome,
        correct_score: Decimal,
        category: ErrorCategory | None,
        note: str,
    ) -> None:
        record = self.get_record(record_id)
        with self.connect() as connection:
            raw = connection.execute(
                "SELECT result_json FROM trial_records WHERE record_id = ?", (record_id,)
            ).fetchone()
            maximum = Decimal(str(json.loads(raw["result_json"])["max_score"]))
            if correct_score < 0 or correct_score > maximum:
                raise ValueError(f"正确分数必须在 0～{maximum} 之间")
            connection.execute(
                """UPDATE trial_records
                SET correct_score = ?, outcome = ?, error_category = ?, note = ?
                WHERE record_id = ?""",
                (str(correct_score), outcome.value, category.value if category else None, note.strip(), record.record_id),
            )

    def get_record(self, record_id: str) -> TrialRecord:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM trial_records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            raise KeyError(f"试改记录不存在：{record_id}")
        return TrialRecord(
            row["record_id"], row["session_id"], row["sequence"], bool(row["need_review"]),
            bool(row["submitted"]), Decimal(row["ai_score"]),
            Decimal(row["correct_score"]) if row["correct_score"] is not None else None,
            ReviewOutcome(row["outcome"]), ErrorCategory(row["error_category"]) if row["error_category"] else None,
            row["note"], row["screenshot_path"],
        )

    def metrics(self, session_id: str) -> TrialMetrics:
        with self.connect() as connection:
            session = connection.execute(
                "SELECT target_count, error_threshold_percent FROM trial_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise KeyError(f"试改会话不存在：{session_id}")
            rows = connection.execute(
                "SELECT need_review, submitted, outcome FROM trial_records WHERE session_id = ?", (session_id,)
            ).fetchall()
        processed = len(rows)
        automatic = sum(not bool(row["need_review"]) and bool(row["submitted"]) for row in rows)
        direct = sum(
            not bool(row["need_review"]) and bool(row["submitted"])
            and row["outcome"] != ReviewOutcome.AI_ERROR.value for row in rows
        )
        requested = sum(bool(row["need_review"]) for row in rows)
        correct = sum(
            bool(row["need_review"]) and row["outcome"] == ReviewOutcome.AI_CORRECT.value for row in rows
        )
        errors = sum(row["outcome"] == ReviewOutcome.AI_ERROR.value for row in rows)
        unreported = sum(
            row["outcome"] == ReviewOutcome.AI_ERROR.value
            and not bool(row["need_review"]) and bool(row["submitted"]) for row in rows
        )
        return TrialMetrics(
            int(session["target_count"]), Decimal(session["error_threshold_percent"]), processed,
            direct, automatic, requested, correct, errors, unreported,
        )

    def error_category_counts(self, session_id: str) -> dict[str, int]:
        counts = {category.value: 0 for category in ErrorCategory}
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT error_category, COUNT(*) AS total
                FROM trial_records
                WHERE session_id = ? AND outcome = ?
                GROUP BY error_category""",
                (session_id, ReviewOutcome.AI_ERROR.value),
            ).fetchall()
        for row in rows:
            if row["error_category"] in counts:
                counts[row["error_category"]] = int(row["total"])
        return counts

    def latest_qualifying_session(self, task: Task) -> TrialSession | None:
        fingerprint = grading_fingerprint(task)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM trial_sessions
                WHERE task_id = ? AND rule_version = ? AND grading_fingerprint = ?
                ORDER BY started_at DESC""",
                (task.task_id, task.rule_version, fingerprint),
            ).fetchall()
        for row in rows:
            metrics = self.metrics(row["session_id"])
            with self.connect() as connection:
                unresolved_reviews = connection.execute(
                    """SELECT COUNT(*) AS total FROM trial_records
                    WHERE session_id = ? AND need_review = 1
                    AND (outcome = ? OR submitted = 0)""",
                    (row["session_id"], ReviewOutcome.UNREVIEWED.value),
                ).fetchone()["total"]
            if metrics.meets_reference_condition and not unresolved_reviews:
                return TrialSession(
                    row["session_id"], row["task_id"], int(row["target_count"]),
                    Decimal(row["error_threshold_percent"]), row["started_at"],
                    int(row["rule_version"]), row["grading_fingerprint"],
                )
        return None
