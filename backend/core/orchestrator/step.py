from abc import ABC, abstractmethod

from core.orchestrator.context import Context


class Step(ABC):
    name: str = "step"

    @abstractmethod
    def run(self, ctx: Context) -> Context: ...
