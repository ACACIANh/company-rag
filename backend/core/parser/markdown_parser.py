from core.parser.base import DocumentParser


class MarkdownParser(DocumentParser):
    """Markdown 원본을 그대로 통과시킨다 (md → md, ADR-0013 D2)."""

    def parse(self, raw: bytes) -> str:
        return raw.decode("utf-8")
