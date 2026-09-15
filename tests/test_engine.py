import asyncio
from pathlib import Path

from app.ai.base import AIProvider
from app.ai.schemas import GradeRequest, GradeResult, validate_grade_result
from app.core.grading_engine import GradingEngine, list_images

from .helpers import make_task, valid_result


class FakeProvider(AIProvider):
    async def grade(self, request: GradeRequest) -> GradeResult:
        return validate_grade_result(valid_result(), request.task)


class FailingProvider(AIProvider):
    async def grade(self, request: GradeRequest) -> GradeResult:
        raise RuntimeError("network down")


def test_dry_run_returns_result_without_automation(tmp_path: Path) -> None:
    image = tmp_path / "answer.png"
    image.write_bytes(b"png")
    record = asyncio.run(GradingEngine(FakeProvider()).dry_run(make_task(), image))
    assert record.error is None
    assert record.result and record.result.total_score == 2


def test_dry_run_records_provider_error(tmp_path: Path) -> None:
    image = tmp_path / "answer.png"
    image.write_bytes(b"png")
    record = asyncio.run(GradingEngine(FailingProvider()).dry_run(make_task(), image))
    assert record.result is None
    assert record.error == "network down"


def test_batch_path_handles_twenty_images_serially(tmp_path: Path) -> None:
    images = []
    for index in range(20):
        image = tmp_path / f"answer-{index:02}.png"
        image.write_bytes(b"png")
        images.append(image)
    records = asyncio.run(GradingEngine(FakeProvider()).batch_dry_run(make_task(), images))
    assert len(records) == 20
    assert all(record.error is None for record in records)


def test_image_listing_filters_and_sorts(tmp_path: Path) -> None:
    for name in ("b.jpg", "a.png", "ignore.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [path.name for path in list_images(tmp_path)] == ["a.png", "b.jpg"]
