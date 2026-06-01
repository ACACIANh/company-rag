import os

from core.loader.base import DocumentLoader
from core.models import Document


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
                folder = os.path.dirname(rel)
                doc_path = "/" + folder.replace(os.sep, "/") if folder else "/"
                with open(full, encoding="utf-8") as f:
                    text = f.read()
                docs.append(Document(text=text, source=rel, metadata={"path": doc_path}))
        return docs
