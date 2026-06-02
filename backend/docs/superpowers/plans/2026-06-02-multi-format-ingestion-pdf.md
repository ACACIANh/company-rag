# 다중 포맷 인제스천(PDF) + 원본 보관/다운로드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF를 RAG 검색 대상에 추가하고, 원본 파일을 `document_originals`에 보관해 권한 검증된 다운로드 API로 제공한다 (ADR-0013 D1~D5).

**Architecture:** 포맷 의존 코드를 신규 `core/parser/`(ABC+Factory)에 격리. `MultiFormatLoader`가 워킹+raw bytes를 읽어 파서로 markdown화하고 `Document(raw, mime)`로 전달. `Indexer`는 `original_store` 주입 시 원본을 `document_originals`(신규)에 버전 저장. 다운로드 API는 검색과 동일한 `get_readable_folders` 정확 매칭으로 권한 재검증. 기존 검색 경로·청크 테이블·`MarkdownLoader`는 무수정.

**Tech Stack:** Python 3.11+, `pypdf`, asyncpg(bytea), FastAPI(StreamingResponse), pytest(mock pool 패턴).

작업 디렉토리는 항상 `backend/`. 인터프리터 `.venv/bin/python`. DB 단위테스트는 기존 `tests/core/test_document_version_store.py`의 `_make_pool()` mock 패턴을 따른다(실 PG 미사용).

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `pyproject.toml` | `pypdf` 의존성 | 수정 |
| `core/parser/base.py` | `DocumentParser` ABC | 신규 |
| `core/parser/markdown_parser.py` | bytes→str pass-through | 신규 |
| `core/parser/pdf_parser.py` | pypdf 추출 | 신규 |
| `core/parser/factory.py` | 확장자→파서, mime_for | 신규 |
| `core/parser/__init__.py` | export | 신규 |
| `core/models.py` | `Document.raw`/`.mime` 필드 | 수정 |
| `core/loader/multi_format_loader.py` | 워킹+raw+mime | 신규 |
| `core/loader/__init__.py` | export 추가 | 수정 |
| `core/document_original/base.py` | `DocumentOriginalStore` ABC + `OriginalRecord` | 신규 |
| `core/document_original/postgres_store.py` | `document_originals` 구현 | 신규 |
| `core/document_original/__init__.py` | export | 신규 |
| `core/indexer/indexer.py` | `original_store` 옵션 | 수정 |
| `app/api/documents.py` | 다운로드 라우터 | 신규 |
| `app/api/deps.py` | `get_original_store` | 수정 |
| `app/api/chat.py` | ensure_table + app.state + include_router | 수정 |
| `app/ingestion/indexer.py` | loader 교체 + original_store 주입 | 수정 |
| `docs/superpowers/decisions/ADR-0013-*.md` | §4 정정 + Status | 수정 |

---

## Task 1: pypdf 의존성 추가

**Files:** Modify `pyproject.toml`

- [ ] **Step 1:** `pyproject.toml` dependencies의 `"sentence-transformers>=2.0,<6",` 줄 다음에 추가:

```toml
    "pypdf>=4.0,<6",
```

- [ ] **Step 2:** Run: `.venv/bin/pip install "pypdf>=4.0,<6"` → Expected: `Successfully installed pypdf-...`
- [ ] **Step 3:** Run: `.venv/bin/python -c "import pypdf; print(pypdf.__version__)"` → Expected: 버전 출력
- [ ] **Step 4:** Commit:

```bash
git add pyproject.toml && git commit -m "build: add pypdf dependency for PDF ingestion (ADR-0013)"
```

---

## Task 2: DocumentParser ABC + MarkdownParser

**Files:** Create `core/parser/base.py`, `core/parser/markdown_parser.py`, `core/parser/__init__.py`; Test `tests/core/test_parser.py`

- [ ] **Step 1: 실패 테스트** — `tests/core/test_parser.py`:

```python
import pytest

from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


def test_markdown_parser_implements_abc():
    assert issubclass(MarkdownParser, DocumentParser)


def test_markdown_parser_decodes_utf8_passthrough():
    raw = "# 제목\n본문".encode("utf-8")
    assert MarkdownParser().parse(raw) == "# 제목\n본문"
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -v` → FAIL (`No module named 'core.parser'`)
- [ ] **Step 3: 구현**

`core/parser/base.py`:

```python
from abc import ABC, abstractmethod


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, raw: bytes) -> str:
        """원본 bytes를 통일 중간표현(Markdown 문자열)으로 변환한다."""
        ...
```

`core/parser/markdown_parser.py`:

```python
from core.parser.base import DocumentParser


class MarkdownParser(DocumentParser):
    """Markdown 원본을 그대로 통과시킨다 (md → md, ADR-0013 D2)."""

    def parse(self, raw: bytes) -> str:
        return raw.decode("utf-8")
```

`core/parser/__init__.py`:

```python
from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser

__all__ = ["DocumentParser", "MarkdownParser"]
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -v` → PASS (2)
- [ ] **Step 5:** Commit:

```bash
git add core/parser/base.py core/parser/markdown_parser.py core/parser/__init__.py tests/core/test_parser.py
git commit -m "feat(parser): add DocumentParser ABC + MarkdownParser passthrough (ADR-0013 D2)"
```

---

## Task 3: PdfParser

**Files:** Create `core/parser/pdf_parser.py`; Test 추가 `tests/core/test_parser.py`

- [ ] **Step 1: 실패 테스트 추가** — `tests/core/test_parser.py` 끝에:

```python
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
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -k pdf -v` → FAIL
- [ ] **Step 3: 구현** — `core/parser/pdf_parser.py`:

```python
import io

from pypdf import PdfReader

from core.parser.base import DocumentParser


class PdfParser(DocumentParser):
    """PDF 원본을 페이지별 텍스트로 추출해 개행으로 연결한다.

    표/이미지 구조 보존은 ADR-0013 §6 후속. 현재는 텍스트 추출 수준.
    """

    def parse(self, raw: bytes) -> str:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -k pdf -v` → PASS (2). 만약 `_make_pdf_bytes`에서 텍스트가 추출되지 않으면 fixture를 `tests/core/fixtures/sample.pdf`(텍스트 "HelloPdf" 포함 고정 파일)로 대체하고 테스트만 그 파일을 읽도록 수정한다. `PdfParser` 구현은 변경 금지.
- [ ] **Step 5:** Commit:

```bash
git add core/parser/pdf_parser.py tests/core/test_parser.py
git commit -m "feat(parser): add PdfParser via pypdf text extraction (ADR-0013 D3)"
```

---

## Task 4: ParserFactory (+ mime_for)

**Files:** Create `core/parser/factory.py`; Modify `core/parser/__init__.py`; Test 추가

- [ ] **Step 1: 실패 테스트 추가** — `tests/core/test_parser.py` 끝에:

```python
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
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -k factory -v` → FAIL
- [ ] **Step 3: 구현** — `core/parser/factory.py`:

```python
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
```

`core/parser/__init__.py` 교체:

```python
from core.parser.base import DocumentParser
from core.parser.factory import ParserFactory
from core.parser.markdown_parser import MarkdownParser
from core.parser.pdf_parser import PdfParser

__all__ = ["DocumentParser", "MarkdownParser", "PdfParser", "ParserFactory"]
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_parser.py -v` → PASS (전체)
- [ ] **Step 5:** Commit:

```bash
git add core/parser/factory.py core/parser/__init__.py tests/core/test_parser.py
git commit -m "feat(parser): add ParserFactory ext->parser dispatch + mime_for (ADR-0013 D3)"
```

---

## Task 5: Document 모델에 raw/mime 추가

**Files:** Modify `core/models.py`; Test `tests/core/test_models.py`

- [ ] **Step 1: 실패 테스트 추가** — `tests/core/test_models.py` 끝에:

```python
def test_document_raw_mime_default_none():
    from core.models import Document

    d = Document(text="t", source="s")
    assert d.raw is None
    assert d.mime is None


def test_document_accepts_raw_mime():
    from core.models import Document

    d = Document(text="t", source="s", raw=b"\x01\x02", mime="application/pdf")
    assert d.raw == b"\x01\x02"
    assert d.mime == "application/pdf"
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_models.py -k document_ -v` → FAIL (`unexpected keyword argument 'raw'`)
- [ ] **Step 3: 구현** — `core/models.py`의 `Document`를 교체:

```python
@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)
    raw: bytes | None = None
    mime: str | None = None
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_models.py -v` → PASS
- [ ] **Step 5:** Commit:

```bash
git add core/models.py tests/core/test_models.py
git commit -m "feat(models): add optional raw/mime fields to Document (ADR-0013 D4)"
```

---

## Task 6: MultiFormatLoader (raw/mime 포함)

**Files:** Create `core/loader/multi_format_loader.py`; Modify `core/loader/__init__.py`; Test `tests/core/test_multi_format_loader.py`

- [ ] **Step 1: 실패 테스트** — `tests/core/test_multi_format_loader.py`:

```python
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
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_multi_format_loader.py -v` → FAIL
- [ ] **Step 3: 구현** — `core/loader/multi_format_loader.py`:

```python
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
```

`core/loader/__init__.py` 교체:

```python
from core.loader.base import DocumentLoader
from core.loader.markdown_loader import MarkdownLoader
from core.loader.multi_format_loader import MultiFormatLoader

__all__ = ["DocumentLoader", "MarkdownLoader", "MultiFormatLoader"]
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_multi_format_loader.py -v` → PASS (6)
- [ ] **Step 5:** Commit:

```bash
git add core/loader/multi_format_loader.py core/loader/__init__.py tests/core/test_multi_format_loader.py
git commit -m "feat(loader): add MultiFormatLoader with raw/mime via ParserFactory (ADR-0013 D1)"
```

---

## Task 7: DocumentOriginalStore (ABC + Postgres)

**Files:** Create `core/document_original/base.py`, `core/document_original/postgres_store.py`, `core/document_original/__init__.py`; Test `tests/core/test_document_original_store.py`

- [ ] **Step 1: 실패 테스트** — `tests/core/test_document_original_store.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_pool():
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_ensure_table_creates_document_originals():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    await PostgresDocumentOriginalStore(pool).ensure_table()
    sql = conn.execute.call_args_list[0][0][0]
    assert "CREATE TABLE IF NOT EXISTS document_originals" in sql
    assert "PRIMARY KEY (document_id, version)" in sql


@pytest.mark.asyncio
async def test_save_first_version_inserts_version_1():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value=None)  # 기존 버전 없음
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"data"
    )
    insert_sql = conn.execute.call_args[0][0]
    assert "INSERT INTO document_originals" in insert_sql
    assert conn.execute.call_args[0][2] == 1  # version 인자


@pytest.mark.asyncio
async def test_save_same_hash_skips_insert():
    import hashlib

    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    h = hashlib.sha256(b"data").hexdigest()
    conn.fetchrow = AsyncMock(return_value={"version": 3, "content_hash": h})
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"data"
    )
    conn.execute.assert_not_awaited()  # 동일 hash → insert 없음


@pytest.mark.asyncio
async def test_save_changed_hash_bumps_version():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value={"version": 3, "content_hash": "old"})
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"newdata"
    )
    assert conn.execute.call_args[0][2] == 4  # version+1


@pytest.mark.asyncio
async def test_get_latest_returns_record():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value={
        "document_id": "/c/eng/a.pdf", "version": 2, "folder_path": "/c/eng",
        "filename": "a.pdf", "mime": "application/pdf",
        "original_file": b"data", "content_hash": "h",
    })
    rec = await PostgresDocumentOriginalStore(pool).get_latest("/c/eng/a.pdf")
    assert rec.folder_path == "/c/eng"
    assert rec.original_file == b"data"
    assert rec.filename == "a.pdf"


@pytest.mark.asyncio
async def test_get_latest_missing_returns_none():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    assert await PostgresDocumentOriginalStore(pool).get_latest("/nope") is None
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_document_original_store.py -v` → FAIL
- [ ] **Step 3: 구현**

`core/document_original/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OriginalRecord:
    document_id: str
    version: int
    folder_path: str
    filename: str
    mime: str
    original_file: bytes
    content_hash: str


class DocumentOriginalStore(ABC):
    """원본 파일(bytea) 보관소. document_id별 버전 이력 (ADR-0013 D4)."""

    @abstractmethod
    async def ensure_table(self) -> None: ...

    @abstractmethod
    async def save(
        self, document_id: str, folder_path: str, filename: str, mime: str, raw: bytes
    ) -> None: ...

    @abstractmethod
    async def get_latest(self, document_id: str) -> OriginalRecord | None: ...
```

`core/document_original/postgres_store.py`:

```python
import hashlib

import asyncpg

from core.document_original.base import DocumentOriginalStore, OriginalRecord


class PostgresDocumentOriginalStore(DocumentOriginalStore):
    """document_originals 테이블 구현. content_hash로 변경 감지·버전 관리."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_originals (
                    document_id   TEXT        NOT NULL,
                    version       INT         NOT NULL,
                    folder_path   TEXT        NOT NULL,
                    filename      TEXT        NOT NULL,
                    mime          TEXT        NOT NULL,
                    original_file BYTEA       NOT NULL,
                    content_hash  TEXT        NOT NULL,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (document_id, version)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_originals_folder "
                "ON document_originals (folder_path text_pattern_ops)"
            )

    async def save(
        self, document_id: str, folder_path: str, filename: str, mime: str, raw: bytes
    ) -> None:
        content_hash = hashlib.sha256(raw).hexdigest()
        async with self._pool.acquire() as conn:
            latest = await conn.fetchrow(
                "SELECT version, content_hash FROM document_originals "
                "WHERE document_id = $1 ORDER BY version DESC LIMIT 1",
                document_id,
            )
            if latest is not None and latest["content_hash"] == content_hash:
                return  # 동일 원본 → 재저장 skip
            next_version = (latest["version"] + 1) if latest is not None else 1
            await conn.execute(
                "INSERT INTO document_originals "
                "(document_id, version, folder_path, filename, mime, original_file, content_hash) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                document_id, next_version, folder_path, filename, mime, raw, content_hash,
            )

    async def get_latest(self, document_id: str) -> OriginalRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT document_id, version, folder_path, filename, mime, "
                "original_file, content_hash FROM document_originals "
                "WHERE document_id = $1 ORDER BY version DESC LIMIT 1",
                document_id,
            )
        if row is None:
            return None
        return OriginalRecord(
            document_id=row["document_id"],
            version=row["version"],
            folder_path=row["folder_path"],
            filename=row["filename"],
            mime=row["mime"],
            original_file=row["original_file"],
            content_hash=row["content_hash"],
        )
```

`core/document_original/__init__.py`:

```python
from core.document_original.base import DocumentOriginalStore, OriginalRecord
from core.document_original.postgres_store import PostgresDocumentOriginalStore

__all__ = ["DocumentOriginalStore", "OriginalRecord", "PostgresDocumentOriginalStore"]
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_document_original_store.py -v` → PASS (6)
- [ ] **Step 5:** Commit:

```bash
git add core/document_original tests/core/test_document_original_store.py
git commit -m "feat(original): add DocumentOriginalStore for bytea original retention (ADR-0013 D4)"
```

---

## Task 8: Indexer에 original_store 옵션 추가

**Files:** Modify `core/indexer/indexer.py`; Test `tests/core/test_indexer.py`

- [ ] **Step 1: 실패 테스트 추가** — `tests/core/test_indexer.py` 끝에:

```python
@pytest.mark.asyncio
async def test_index_saves_originals_when_store_given():
    from unittest.mock import AsyncMock, MagicMock

    from core.indexer.indexer import Indexer
    from core.models import Chunk, Document

    loader = MagicMock()
    loader.load = MagicMock(return_value=[
        Document(text="hello", source="eng/a.pdf", metadata={"path": "/c/eng"},
                 raw=b"raw", mime="application/pdf"),
    ])
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[Chunk(text="hello", source="eng/a.pdf", chunk_id="1")])
    embedder = MagicMock()
    embedder.embed_batch = MagicMock(return_value=[[0.1]])
    store = AsyncMock()
    original_store = AsyncMock()

    await Indexer(loader, chunker, embedder, store, original_store=original_store).index("p")

    original_store.save.assert_awaited_once_with(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"raw"
    )


@pytest.mark.asyncio
async def test_index_without_original_store_does_not_fail():
    from unittest.mock import AsyncMock, MagicMock

    from core.indexer.indexer import Indexer
    from core.models import Chunk, Document

    loader = MagicMock()
    loader.load = MagicMock(return_value=[Document(text="x", source="a.md", metadata={"path": "/c"})])
    chunker = MagicMock()
    chunker.chunk = MagicMock(return_value=[Chunk(text="x", source="a.md", chunk_id="1")])
    embedder = MagicMock()
    embedder.embed_batch = MagicMock(return_value=[[0.1]])
    store = AsyncMock()

    n = await Indexer(loader, chunker, embedder, store).index("p")
    assert n == 1
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/core/test_indexer.py -k original -v` → FAIL (`unexpected keyword argument 'original_store'`)
- [ ] **Step 3: 구현** — `core/indexer/indexer.py` 교체:

```python
from core.chunker.base import Chunker
from core.document_original.base import DocumentOriginalStore
from core.embedder.base import Embedder
from core.loader.base import DocumentLoader
from core.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        original_store: DocumentOriginalStore | None = None,
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._original_store = original_store

    async def index(self, path: str) -> int:
        docs = self._loader.load(path)
        if self._original_store is not None:
            for d in docs:
                if d.raw is not None and d.mime is not None:
                    folder_path = d.metadata.get("path", "")
                    filename = d.source.rsplit("/", 1)[-1]
                    await self._original_store.save(
                        folder_path + "/" + filename, folder_path, filename, d.mime, d.raw
                    )
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        await self._store.add(chunks, embeddings)
        return len(chunks)
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/core/test_indexer.py -v` → PASS (기존 + 신규 전부)
- [ ] **Step 5:** Commit:

```bash
git add core/indexer/indexer.py tests/core/test_indexer.py
git commit -m "feat(indexer): optionally persist originals via DocumentOriginalStore (ADR-0013 D4)"
```

---

## Task 9: 다운로드 API (권한 재검증)

**Files:** Create `app/api/documents.py`; Modify `app/api/deps.py`; Test `tests/app/test_documents_api.py`

핸들러를 라우트 함수로 두되, 단위테스트는 함수를 직접 await 호출(mock 의존성 주입)한다.

- [ ] **Step 1: deps에 get_original_store 추가** — `app/api/deps.py`의 `get_session_store` 함수 아래에 추가:

```python
def get_original_store(request: Request):
    return request.app.state.original_store
```

- [ ] **Step 2: 실패 테스트** — `tests/app/test_documents_api.py`:

```python
import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException


def _user(uid="u1"):
    return {"user_id": uid, "roles": ["employee"], "departments": []}


def _rec(folder="/c/eng"):
    from core.document_original.base import OriginalRecord

    return OriginalRecord(
        document_id="/c/eng/a.pdf", version=1, folder_path=folder,
        filename="a.pdf", mime="application/pdf",
        original_file=b"PDFDATA", content_hash="h",
    )


@pytest.mark.asyncio
async def test_download_allowed_folder_returns_stream():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/eng", "/c/hr"])
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=_rec("/c/eng"))

    resp = await download_document(
        document_id="/c/eng/a.pdf", user=_user(), fga_client=fga, original_store=store
    )
    assert resp.media_type == "application/pdf"
    assert 'filename="a.pdf"' in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_forbidden_folder_404():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/hr"])  # eng 비가시
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=_rec("/c/eng"))

    with pytest.raises(HTTPException) as exc:
        await download_document(
            document_id="/c/eng/a.pdf", user=_user(), fga_client=fga, original_store=store
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_document_404():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/eng"])
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await download_document(
            document_id="/c/eng/missing.pdf", user=_user(), fga_client=fga, original_store=store
        )
    assert exc.value.status_code == 404
```

- [ ] **Step 3: 구현** — `app/api/documents.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.auth.base import AuthUser
from core.document_original.base import DocumentOriginalStore
from core.fga.client import FGAClient
from app.api.deps import get_current_user, get_fga_client, get_original_store

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/download")
async def download_document(
    document_id: str = Query(...),
    user: AuthUser = Depends(get_current_user),
    fga_client: FGAClient = Depends(get_fga_client),
    original_store: DocumentOriginalStore = Depends(get_original_store),
) -> StreamingResponse:
    rec = await original_store.get_latest(document_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Document not found")
    folders = await fga_client.get_readable_folders(user["user_id"])
    # 검색 pre-filter와 동일한 정확 매칭. 비가시 폴더는 존재를 숨겨 404.
    if rec.folder_path not in folders:
        raise HTTPException(status_code=404, detail="Document not found")
    return StreamingResponse(
        iter([rec.original_file]),
        media_type=rec.mime,
        headers={"Content-Disposition": f'attachment; filename="{rec.filename}"'},
    )
```

- [ ] **Step 4:** `tests/app/__init__.py`가 없으면 생성(빈 파일). Run `.venv/bin/python -m pytest tests/app/test_documents_api.py -v` → PASS (3)
- [ ] **Step 5:** Commit:

```bash
git add app/api/documents.py app/api/deps.py tests/app/test_documents_api.py tests/app/__init__.py
git commit -m "feat(api): add permission-checked document download endpoint (ADR-0013 D4, §5)"
```

---

## Task 10: 앱 조립 — ensure_table + app.state + 라우터 + ingestion 주입

**Files:** Modify `app/api/chat.py`, `app/ingestion/indexer.py`

- [ ] **Step 1: chat.py — import 추가** — 기존 `from core.document_version.postgres_store import PostgresDocumentVersionStore` 아래에:

```python
from core.document_original.postgres_store import PostgresDocumentOriginalStore
from app.api.documents import router as documents_router
```

- [ ] **Step 2: chat.py — ensure_table + app.state 등록** — `await PostgresDocumentVersionStore(pool).ensure_table()` 아래에:

```python
    original_store = PostgresDocumentOriginalStore(pool)
    await original_store.ensure_table()
```

그리고 `app.state.graph = graph` 아래(같은 들여쓰기)에:

```python
        app.state.original_store = original_store
```

- [ ] **Step 3: chat.py — 라우터 등록** — `app.include_router(sessions_router)` 아래에:

```python
app.include_router(documents_router)
```

- [ ] **Step 4: ingestion 주입** — `app/ingestion/indexer.py`:

`from core.loader import MarkdownLoader` → `from core.loader import MultiFormatLoader`
그 아래에 추가: `from core.document_original.postgres_store import PostgresDocumentOriginalStore`

`loader = MarkdownLoader(base_path=base_path)` → `loader = MultiFormatLoader(base_path=base_path)`

`store = create_vector_store(config, pool)` 아래에:

```python
    original_store = PostgresDocumentOriginalStore(pool)
    await original_store.ensure_table()
```

`Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store,)` 호출을:

```python
    await Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        original_store=original_store,
    ).index(docs_path)
```

- [ ] **Step 5: 회귀 — 전체 테스트 + import 확인**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (전체)

Run: `.venv/bin/python -c "import app.api.chat"`
Expected: 에러 없음 (라우터/조립 import 정상)

- [ ] **Step 6:** Commit:

```bash
git add app/api/chat.py app/ingestion/indexer.py
git commit -m "feat(api): wire original_store into app + ingestion, register download router (ADR-0013)"
```

---

## Task 11: ADR-0013 §4 정정 + Status 갱신 + 인덱스 재생성

**Files:** Modify `docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md`, `docs/superpowers/decisions/README.md`(자동)

- [ ] **Step 1: Status 줄 교체** — `ADR-0013-multi-format-ingestion.md:3`:

```markdown
> **Status**: 🟡 보류 — 미구현 (현재 Markdown 인제스천만)
```
→
```markdown
> **Status**: 🟢 적용완료 — D1~D5 적용 (PDF 파서 격리 + 원본 bytea 보관 + 권한검증 다운로드). 페이지 단위 역추적·S3 이전은 후속.
```

- [ ] **Step 2: §4 데이터 모델 정정** — §4의 `documents`/`chunks` 의사 스키마 블록을 실제 구현으로 교체. `documents`는 청크 테이블이며 원본은 `document_originals`에 별도 보관함을 명시:

```markdown
## 4. 데이터 모델 (실제 구현)

> 최초 제안은 documents에 원본+content를 통합했으나, 실제 `documents`는 청크 테이블(pgvector)이라
> 원본은 신규 `document_originals` 테이블에 분리 보관한다.

document_originals  (원본 보관, 불변, D4)
├── document_id   TEXT   ← folder_path + "/" + filename (안정 키)
├── version       INT    ← content_hash 변경 시 +1
├── folder_path   TEXT   ← 권한 경계용 (documents.path와 동일 체계, 정확 매칭)
├── filename      TEXT   ← Content-Disposition
├── mime          TEXT
├── original_file BYTEA  ← 원본, 불변
├── content_hash  TEXT   ← SHA-256, 변경 감지/중복 방지
└── PRIMARY KEY (document_id, version)

documents (기존 청크 테이블, 무변경): chunk_id, content(청크), embedding, path, source
```

- [ ] **Step 3: 인덱스 재생성** — Run: `.venv/bin/python -m scripts.gen_adr_index` → Expected: README.md 재생성(0013이 🟢)
- [ ] **Step 4:** Commit:

```bash
git add docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0013 D1~D5 적용완료 + §4를 실제 document_originals 스키마로 정정"
```

---

## 최종 검증 (전체 DoD)

- [ ] **전체 테스트**: `.venv/bin/python -m pytest tests/ -q` → 전부 PASS
- [ ] **lint**: `.venv/bin/ruff check core/parser core/loader core/document_original core/indexer app/api/documents.py app/ingestion/indexer.py` → 통과
- [ ] **앱 import**: `.venv/bin/python -c "import app.api.chat"` → 에러 없음
- [ ] eval 회귀: loader/Indexer 변경은 기존 md 인덱싱 결과 불변(파서 pass-through, original_store는 별도 경로). 기존 코퍼스 점수 불변 기대.
