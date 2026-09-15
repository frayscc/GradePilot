from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.safety import SafetyController, SubmissionPermit
from app.core.screenshot import VisualSignature


class PageTransitionError(RuntimeError):
    """No positive visual evidence that the next answer loaded."""


@dataclass(frozen=True)
class PageSnapshot:
    answer: VisualSignature
    submit_button: VisualSignature
    page_marker: VisualSignature | None = None


class GradingPlatform(ABC):
    @abstractmethod
    def capture_answer(self, output: Path) -> Path: ...

    @abstractmethod
    def snapshot_page(self) -> PageSnapshot: ...

    @abstractmethod
    def assert_same_answer(self, before: PageSnapshot) -> None: ...

    @abstractmethod
    def enter_score(self, permit: SubmissionPermit) -> None: ...

    @abstractmethod
    def submit(self, permit: SubmissionPermit) -> None: ...

    @abstractmethod
    def wait_next(self, before: PageSnapshot, safety: SafetyController) -> None: ...
