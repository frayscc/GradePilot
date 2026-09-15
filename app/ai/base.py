from abc import ABC, abstractmethod

from .schemas import GradeRequest, GradeResult


class ProviderError(RuntimeError):
    """The provider request failed; no score may be used."""


class AIProvider(ABC):
    @abstractmethod
    async def grade(self, request: GradeRequest) -> GradeResult: ...
