from abc import ABC, abstractmethod

from shared.models import Document


class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: str) -> list[Document]: ...
