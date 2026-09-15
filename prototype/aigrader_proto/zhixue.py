from dataclasses import dataclass

from .automation import AutomationContext, Point, SafeWebAutomation
from .models import GradeResult
from .platform import GradingPlatform


@dataclass(frozen=True)
class ZhixueCoordinates:
    score_input: Point
    submit_button: Point


class ZhixuePlatform(GradingPlatform):
    """Phase 0 coordinate adapter; it intentionally knows nothing about the GUI."""

    def __init__(self, coordinates: ZhixueCoordinates, automation: SafeWebAutomation) -> None:
        self.coordinates = coordinates
        self.automation = automation

    def enter_score(self, result: GradeResult, context: AutomationContext) -> None:
        self.automation.enter_score(self.coordinates.score_input, result, context)

    def submit(self, result: GradeResult, context: AutomationContext) -> None:
        self.automation.submit(self.coordinates.submit_button, result, context)
