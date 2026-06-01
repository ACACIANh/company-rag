import os

from core.loader.base import DocumentLoader
from core.models import Document


class MarkdownLoader(DocumentLoader):
    def __init__(self, base_path: str = "") -> None:
        # base_path는 생성된 doc path의 prefix가 된다 (예: "/company"). 끝 슬래시는 무시.
        self._base_path = base_path.rstrip("/")

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
                if folder:
                    doc_path = self._base_path + "/" + folder.replace(os.sep, "/")
                else:
                    doc_path = self._base_path or "/"
                with open(full, encoding="utf-8") as f:
                    text = f.read()
                docs.append(Document(text=text, source=rel, metadata={"path": doc_path}))
        return docs
