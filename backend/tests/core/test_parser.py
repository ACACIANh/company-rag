import pytest

from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


def test_markdown_parser_implements_abc():
    assert issubclass(MarkdownParser, DocumentParser)


def test_markdown_parser_decodes_utf8_passthrough():
    raw = "# 제목\n본문".encode("utf-8")
    assert MarkdownParser().parse(raw) == "# 제목\n본문"


def test_factory_returns_markdown_parser_for_md():
    from core.parser.factory import ParserFactory
    from core.parser.markdown_parser import MarkdownParser

    assert isinstance(ParserFactory().get_parser(".md"), MarkdownParser)


def test_factory_unsupported_extension_raises():
    from core.parser.factory import ParserFactory

    with pytest.raises(ValueError):
        ParserFactory().get_parser(".txt")


def test_factory_supported_extensions():
    from core.parser.factory import ParserFactory

    assert set(ParserFactory().supported_extensions()) == {".md"}


def test_factory_mime_for():
    from core.parser.factory import ParserFactory

    assert ParserFactory().mime_for(".md") == "text/markdown"
