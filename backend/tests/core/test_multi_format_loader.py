import pytest

from core.loader.base import DocumentLoader
from core.loader.multi_format_loader import MultiFormatLoader


def test_implements_abc():
    assert issubclass(MultiFormatLoader, DocumentLoader)


def test_loads_markdown_with_raw_and_mime(tmp_path):
    (tmp_path / "a.md").write_text("# A\nhello", encoding="utf-8")
    docs = MultiFormatLoader().load(str(tmp_path))
    assert [d.source for d in docs] == ["a.md"]
    assert docs[0].text == "# A\nhello"
    assert docs[0].raw == "# A\nhello".encode("utf-8")
    assert docs[0].mime == "text/markdown"


def test_ignores_unsupported_extension(tmp_path):
    (tmp_path / "a.md").write_text("md", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nope", encoding="utf-8")
    assert [d.source for d in MultiFormatLoader().load(str(tmp_path))] == ["a.md"]


def test_base_path_prefixes_subfolder(tmp_path):
    sub = tmp_path / "engineering"
    sub.mkdir()
    (sub / "spec.md").write_text("x", encoding="utf-8")
    docs = MultiFormatLoader(base_path="/company").load(str(tmp_path))
    assert docs[0].metadata["path"] == "/company/engineering"


def test_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MultiFormatLoader().load(str(tmp_path / "nope"))


def test_loads_pdf_alongside_md(tmp_path):
    from tests.core.test_parser import _make_pdf_bytes

    (tmp_path / "a.md").write_text("md body", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(_make_pdf_bytes("PdfBody"))
    docs = {d.source: d for d in MultiFormatLoader().load(str(tmp_path))}
    assert docs["a.md"].text == "md body"
    assert "PdfBody" in docs["b.pdf"].text
    assert docs["b.pdf"].mime == "application/pdf"
    assert docs["b.pdf"].raw is not None
