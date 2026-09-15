from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.ai.base import AIProvider
from app.ai.schemas import GradeRequest, GradeResult
from app.data.models import Task


SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@dataclass(frozen=True)
class DryRunRecord:
    image: str
    started_at: str
    latency_ms: int
    result: GradeResult | None
    error: str | None

    def as_dict(self) -> dict:
        return {
            "image": self.image,
            "started_at": self.started_at,
            "latency_ms": self.latency_ms,
            "result": self.result.as_dict() if self.result else None,
            "error": self.error,
        }


class GradingEngine:
    """Phase 1 dry-run engine. It has no dependency on web automation."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def dry_run(self, task: Task, image: Path) -> DryRunRecord:
        started = datetime.now(timezone.utc).isoformat()
        clock = time.perf_counter()
        try:
            result = await self.provider.grade(GradeRequest(task, image))
            return DryRunRecord(str(image), started, round((time.perf_counter() - clock) * 1000), result, None)
        except Exception as exc:
            return DryRunRecord(str(image), started, round((time.perf_counter() - clock) * 1000), None, str(exc))

    async def batch_dry_run(self, task: Task, images: list[Path]) -> list[DryRunRecord]:
        records: list[DryRunRecord] = []
        for image in images:  # V1 deliberately stays serial.
            records.append(await self.dry_run(task, image))
        return records


def list_images(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGES)
