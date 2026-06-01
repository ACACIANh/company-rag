import pytest

from core.loader import MarkdownLoader
from core.loader.base import DocumentLoader


def test_loader_implements_abc():
    assert issubclass(MarkdownLoader, DocumentLoader)


def test_loader_reads_md_files(tmp_path):
    (tmp_path / "a.md").write_text("hello A", encoding="utf-8")
    (tmp_path / "b.md").write_text("hello B", encoding="utf-8")
    docs = MarkdownLoader().load(str(tmp_path))
    sources = sorted(d.source for d in docs)
    assert sources == ["a.md", "b.md"]
    contents = {d.source: d.text for d in docs}
    assert contents["a.md"] == "hello A"
    assert contents["b.md"] == "hello B"


def test_loader_ignores_non_md_files(tmp_path):
    (tmp_path / "a.md").write_text("md content", encoding="utf-8")
    (tmp_path / "b.txt").write_text("not md", encoding="utf-8")
    docs = MarkdownLoader().load(str(tmp_path))
    assert [d.source for d in docs] == ["a.md"]


def test_loader_empty_dir(tmp_path):
    assert MarkdownLoader().load(str(tmp_path)) == []


def test_loader_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MarkdownLoader().load(str(tmp_path / "nope"))


def test_loader_default_path_has_no_prefix(tmp_path):
    sub = tmp_path / "engineering"
    sub.mkdir()
    (sub / "spec.md").write_text("x", encoding="utf-8")
    docs = MarkdownLoader().load(str(tmp_path))
    assert docs[0].metadata["path"] == "/engineering"


def test_loader_base_path_prefixes_subfolder(tmp_path):
    sub = tmp_path / "engineering"
    sub.mkdir()
    (sub / "spec.md").write_text("x", encoding="utf-8")
    docs = MarkdownLoader(base_path="/company").load(str(tmp_path))
    assert docs[0].metadata["path"] == "/company/engineering"


def test_loader_base_path_root_file_is_base(tmp_path):
    (tmp_path / "top.md").write_text("x", encoding="utf-8")
    docs = MarkdownLoader(base_path="/company").load(str(tmp_path))
    assert docs[0].metadata["path"] == "/company"
