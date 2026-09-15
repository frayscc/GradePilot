from abc import ABC, abstractmethod

from .models import GradeRequest, GradeResult


class AIProvider(ABC):
    @abstractmethod
    async def grade(self, request: GradeRequest) -> GradeResult:
        """Grade one answer image or raise; never return an unchecked result."""
