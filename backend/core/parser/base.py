from abc import ABC, abstractmethod


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, raw: bytes) -> str:
        """원본 bytes를 통일 중간표현(Markdown 문자열)으로 변환한다."""
        ...
