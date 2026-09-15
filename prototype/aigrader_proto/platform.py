from abc import ABC, abstractmethod

from .automation import AutomationContext
from .models import GradeResult


class GradingPlatform(ABC):
    @abstractmethod
    def enter_score(self, result: GradeResult, context: AutomationContext) -> None: ...

    @abstractmethod
    def submit(self, result: GradeResult, context: AutomationContext) -> None: ...
