from abc import ABC, abstractmethod

from shared.orchestrator.context import Context


class Step(ABC):
    name: str = "step"

    @abstractmethod
    def run(self, ctx: Context) -> Context: ...
