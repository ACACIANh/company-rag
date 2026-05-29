from abc import ABC, abstractmethod


class CostSink(ABC):
    @abstractmethod
    def record(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
    ) -> None: ...
