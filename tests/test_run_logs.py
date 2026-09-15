from dataclasses import replace
from pathlib import Path

from app.core.automation_session import AutomationRunResult
from app.core.safety import RunState
from app.data.run_logs import RunLogRepository

from .helpers import make_task
from .test_automation_session import parsed_result


def make_record(state: RunState = RunState.WAIT_NEXT) -> AutomationRunResult:
    success = state == RunState.WAIT_NEXT
    return AutomationRunResult(
        index=7,
        state=state,
        result=parsed_result() if state != RunState.API_ERROR else None,
        submitted=success,
        error=None if success else "测试异常",
        started_at="2026-09-16T00:00:00+00:00",
        completed_at="2026-09-16T00:00:01+00:00",
        latency_ms=1384,
        api_success=state != RunState.API_ERROR,
        score_entered=success,
        submit_clicked=success,
    )


def test_normal_log_is_structured_without_retaining_screenshot(tmp_path: Path) -> None:
    repository = RunLogRepository(tmp_path / "logs.db", tmp_path / "exceptions")
    screenshot = tmp_path / "answer.png"
    screenshot.write_bytes(b"student")
    repository.add(make_task(), make_record(), "automatic", screenshot)
    row = repository.records(make_task().task_id, mode="automatic")[0]
    assert row["latency_ms"] == 1384
    assert row["api_success"] == 1
    assert row["score_entered"] == 1
    assert row["submitted"] == 1
    assert row["rule_version"] == 1
    assert row["result_json"]
    assert row["screenshot_path"] is None
    assert list((tmp_path / "exceptions").iterdir()) == []
    assert repository.next_index(make_task().task_id) == 8


def test_exception_log_archives_screenshot(tmp_path: Path) -> None:
    repository = RunLogRepository(tmp_path / "logs.db", tmp_path / "exceptions")
    screenshot = tmp_path / "answer.png"
    screenshot.write_bytes(b"student")
    repository.add(make_task(), make_record(RunState.API_ERROR), "automatic", screenshot)
    row = repository.records(make_task().task_id)[0]
    assert row["api_success"] == 0
    assert row["submitted"] == 0
    assert row["state"] == RunState.API_ERROR.value
    assert Path(row["screenshot_path"]).read_bytes() == b"student"
