import pytest

from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


def test_markdown_parser_implements_abc():
    assert issubclass(MarkdownParser, DocumentParser)


def test_markdown_parser_decodes_utf8_passthrough():
    raw = "# 제목\n본문".encode("utf-8")
    assert MarkdownParser().parse(raw) == "# 제목\n본문"
