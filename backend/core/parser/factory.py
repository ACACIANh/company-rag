from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser
from core.parser.pdf_parser import PdfParser


class ParserFactory:
    """파일 확장자로 DocumentParser 구현체를 선택한다 (ADR-0013 D3)."""

    _MIME = {".md": "text/markdown", ".pdf": "application/pdf"}

    def __init__(self) -> None:
        self._parsers: dict[str, DocumentParser] = {
            ".md": MarkdownParser(),
            ".pdf": PdfParser(),
        }

    def supported_extensions(self) -> list[str]:
        return list(self._parsers.keys())

    def get_parser(self, ext: str) -> DocumentParser:
        parser = self._parsers.get(ext.lower())
        if parser is None:
            raise ValueError(f"지원하지 않는 확장자: {ext}")
        return parser

    def mime_for(self, ext: str) -> str:
        mime = self._MIME.get(ext.lower())
        if mime is None:
            raise ValueError(f"지원하지 않는 확장자: {ext}")
        return mime
