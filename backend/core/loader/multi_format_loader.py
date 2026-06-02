import os

from core.loader.base import DocumentLoader
from core.models import Document
from core.parser.factory import ParserFactory


class MultiFormatLoader(DocumentLoader):
    """디렉토리를 워킹하며 지원 포맷 파일을 파서로 Markdown화하고 원본 bytes를 함께 싣는다.

    포맷 의존 코드는 ParserFactory 뒤 파서에만 격리된다 (ADR-0013 D1).
    """

    def __init__(self, base_path: str = "") -> None:
        # base_path는 생성된 doc path의 prefix가 된다 (예: "/company"). 끝 슬래시는 무시.
        self._base_path = base_path.rstrip("/")
        self._factory = ParserFactory()
        self._supported = set(self._factory.supported_extensions())

    def load(self, path: str) -> list[Document]:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)
        docs: list[Document] = []
        for dirpath, _, filenames in os.walk(path):
            for filename in sorted(filenames):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in self._supported:
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, path)
                folder = os.path.dirname(rel)
                if folder:
                    doc_path = self._base_path + "/" + folder.replace(os.sep, "/")
                else:
                    doc_path = self._base_path or "/"
                with open(full, "rb") as f:
                    raw = f.read()
                text = self._factory.get_parser(ext).parse(raw)
                docs.append(Document(
                    text=text,
                    source=rel,
                    metadata={"path": doc_path},
                    raw=raw,
                    mime=self._factory.mime_for(ext),
                ))
        return docs
