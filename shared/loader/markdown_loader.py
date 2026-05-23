import os

from shared.loader.base import DocumentLoader
from shared.models import Document


class MarkdownLoader(DocumentLoader):
    def load(self, path: str) -> list[Document]:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)
        docs: list[Document] = []
        for dirpath, _, filenames in os.walk(path):
            for filename in sorted(filenames):
                if not filename.endswith(".md"):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, path)
                with open(full, encoding="utf-8") as f:
                    text = f.read()
                docs.append(Document(text=text, source=rel))
        return docs
