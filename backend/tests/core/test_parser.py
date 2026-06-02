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
