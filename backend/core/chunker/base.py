from abc import ABC, abstractmethod

from shared.models import Chunk, Document


class Chunker(ABC):
    @abstractmethod
    def chunk(self, doc: Document) -> list[Chunk]: ...
