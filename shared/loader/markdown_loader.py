import os

from shared.loader.base import DocumentLoader
from shared.models import Document


class MarkdownLoader(DocumentLoader):
    def load(self, path: str) -> list[Document]:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)
        docs: list[Document] = []
        for filename in sorted(os.listdir(path)):
            if not filename.endswith(".md"):
                continue
            full = os.path.join(path, filename)
            with open(full, encoding="utf-8") as f:
                text = f.read()
            docs.append(Document(text=text, source=filename))
        return docs
