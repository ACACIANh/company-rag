from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OriginalRecord:
    document_id: str
    version: int
    folder_path: str
    filename: str
    mime: str
    original_file: bytes
    content_hash: str


class DocumentOriginalStore(ABC):
    """원본 파일(bytea) 보관소. document_id별 버전 이력 (ADR-0013 D4)."""

    @abstractmethod
    async def ensure_table(self) -> None: ...

    @abstractmethod
    async def save(
        self, document_id: str, folder_path: str, filename: str, mime: str, raw: bytes
    ) -> None: ...

    @abstractmethod
    async def get_latest(self, document_id: str) -> OriginalRecord | None: ...
