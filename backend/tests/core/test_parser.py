import pytest

from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


def test_markdown_parser_implements_abc():
    assert issubclass(MarkdownParser, DocumentParser)


def test_markdown_parser_decodes_utf8_passthrough():
    raw = "# 제목\n본문".encode("utf-8")
    assert MarkdownParser().parse(raw) == "# 제목\n본문"


def _make_pdf_bytes(text: str) -> bytes:
    """pypdf로 텍스트 레이어가 있는 최소 PDF를 생성한다 (테스트 fixture)."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    page = writer.pages[0]

    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_pdf_parser_implements_abc():
    from core.parser.base import DocumentParser
    from core.parser.pdf_parser import PdfParser

    assert issubclass(PdfParser, DocumentParser)


def test_pdf_parser_extracts_text():
    from core.parser.pdf_parser import PdfParser

    out = PdfParser().parse(_make_pdf_bytes("HelloPdf"))
    assert "HelloPdf" in out


def test_factory_returns_markdown_parser_for_md():
    from core.parser.factory import ParserFactory
    from core.parser.markdown_parser import MarkdownParser

    assert isinstance(ParserFactory().get_parser(".md"), MarkdownParser)


def test_factory_returns_pdf_parser_for_pdf():
    from core.parser.factory import ParserFactory
    from core.parser.pdf_parser import PdfParser

    assert isinstance(ParserFactory().get_parser(".pdf"), PdfParser)


def test_factory_normalizes_uppercase_extension():
    from core.parser.factory import ParserFactory
    from core.parser.pdf_parser import PdfParser

    assert isinstance(ParserFactory().get_parser(".PDF"), PdfParser)


def test_factory_unsupported_extension_raises():
    from core.parser.factory import ParserFactory

    with pytest.raises(ValueError):
        ParserFactory().get_parser(".txt")


def test_factory_supported_extensions():
    from core.parser.factory import ParserFactory

    assert set(ParserFactory().supported_extensions()) == {".md", ".pdf"}


def test_factory_mime_for():
    from core.parser.factory import ParserFactory

    f = ParserFactory()
    assert f.mime_for(".md") == "text/markdown"
    assert f.mime_for(".PDF") == "application/pdf"
