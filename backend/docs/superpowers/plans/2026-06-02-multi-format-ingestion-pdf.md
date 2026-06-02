# 다중 포맷 문서 인제스천 (PDF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Markdown 전용 인제스천 파이프라인에 PDF를 추가하되, 포맷 의존 코드를 신규 `core/parser/` 계층에만 격리한다 (ADR-0013 D1~D3).

**Architecture:** `DocumentParser` ABC + `ParserFactory`(확장자→파서)를 신규 추가하고, 디렉토리 워킹·path 메타 생성은 신규 `MultiFormatLoader`가 담당한다. 파일 raw bytes를 읽어 파서로 markdown 문자열을 얻은 뒤 기존 `Document`로 만든다. `Indexer`·`Chunker`·`Embedder`·`VectorStore`·권한 필터는 무수정. 주입 지점(`app/ingestion/indexer.py`)에서 loader 한 줄만 교체한다.

**Tech Stack:** Python 3.11+, `pypdf`(PDF 텍스트 추출), pytest.

작업 디렉토리는 항상 `backend/`. 인터프리터는 `.venv/bin/python`.

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `core/parser/base.py` | `DocumentParser` ABC: `parse(raw: bytes) -> str` | 신규 |
| `core/parser/markdown_parser.py` | `MarkdownParser` — bytes utf-8 decode pass-through | 신규 |
| `core/parser/pdf_parser.py` | `PdfParser` — pypdf 페이지 텍스트 추출 | 신규 |
| `core/parser/factory.py` | `ParserFactory` — 확장자→파서, 미지원시 ValueError | 신규 |
| `core/parser/__init__.py` | export | 신규 |
| `core/loader/multi_format_loader.py` | `MultiFormatLoader` — 워킹+path 메타+raw→파서 | 신규 |
| `core/loader/__init__.py` | `MultiFormatLoader` export 추가 | 수정 |
| `app/ingestion/indexer.py:8,18` | loader 주입 교체 | 수정 |
| `pyproject.toml:11~` | `pypdf` 의존성 추가 | 수정 |
| `docs/superpowers/decisions/ADR-0013-*.md` | Status 갱신 | 수정 |

---

## Task 1: pypdf 의존성 추가

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: `pyproject.toml` dependencies 배열에 pypdf 추가**

`sentence-transformers>=2.0,<6",` 줄 바로 다음에 추가:

```toml
    "pypdf>=4.0,<6",
```

- [ ] **Step 2: 설치**

Run: `.venv/bin/pip install "pypdf>=4.0,<6"`
Expected: `Successfully installed pypdf-...`

- [ ] **Step 3: import 확인**

Run: `.venv/bin/python -c "import pypdf; print(pypdf.__version__)"`
Expected: 버전 문자열 출력 (에러 없음)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pypdf dependency for PDF ingestion (ADR-0013)"
```

---

## Task 2: DocumentParser ABC + MarkdownParser

**Files:**
- Create: `core/parser/base.py`
- Create: `core/parser/markdown_parser.py`
- Create: `core/parser/__init__.py`
- Test: `tests/core/test_parser.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/core/test_parser.py`:

```python
import pytest

from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


def test_markdown_parser_implements_abc():
    assert issubclass(MarkdownParser, DocumentParser)


def test_markdown_parser_decodes_utf8_passthrough():
    raw = "# 제목\n본문 텍스트".encode("utf-8")
    assert MarkdownParser().parse(raw) == "# 제목\n본문 텍스트"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.parser'`

- [ ] **Step 3: 최소 구현**

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

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/parser/base.py core/parser/markdown_parser.py core/parser/__init__.py tests/core/test_parser.py
git commit -m "feat(parser): add DocumentParser ABC + MarkdownParser passthrough (ADR-0013 D2)"
```

---

## Task 3: PdfParser

**Files:**
- Create: `core/parser/pdf_parser.py`
- Test: `tests/core/test_parser.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/core/test_parser.py` 끝에 추가. fixture PDF는 pypdf로 즉석 생성:

```python
def _make_pdf_bytes(text: str) -> bytes:
    import io

    from pypdf import PdfWriter

    # 빈 페이지에 텍스트를 직접 그릴 수는 없으므로, reportlab 없이 검증 가능한
    # 최소 경로를 쓴다: pypdf가 텍스트 레이어를 읽을 수 있는 PDF를 생성한다.
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
    )

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    page = writer.pages[0]

    # content stream에 텍스트 그리기 연산자 삽입
    content = DecodedStreamObject()
    content.set_data(
        f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
    )
    page[NameObject("/Contents")] = writer._add_object(content)

    # 기본 Type1 폰트(Helvetica) 리소스 등록
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    page[NameObject("/Resources")] = resources

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_pdf_parser_implements_abc():
    from core.parser.base import DocumentParser
    from core.parser.pdf_parser import PdfParser

    assert issubclass(PdfParser, DocumentParser)


def test_pdf_parser_extracts_text():
    from core.parser.pdf_parser import PdfParser

    raw = _make_pdf_bytes("HelloPdf")
    out = PdfParser().parse(raw)
    assert "HelloPdf" in out
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -k pdf -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.parser.pdf_parser'`

- [ ] **Step 3: 최소 구현**

`core/parser/pdf_parser.py`:

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

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -k pdf -v`
Expected: PASS (2 passed). 만약 `_make_pdf_bytes`의 텍스트 추출이 환경상 실패하면, fixture를 `tests/fixtures/sample.pdf`(텍스트 "HelloPdf" 포함 고정 파일)로 대체하고 `Path(__file__).parent / "fixtures" / "sample.pdf"`를 읽도록 테스트를 수정한다. 구현(`PdfParser`)은 변경하지 않는다.

- [ ] **Step 5: Commit**

```bash
git add core/parser/pdf_parser.py tests/core/test_parser.py
git commit -m "feat(parser): add PdfParser via pypdf text extraction (ADR-0013 D3)"
```

---

## Task 4: ParserFactory

**Files:**
- Create: `core/parser/factory.py`
- Modify: `core/parser/__init__.py`
- Test: `tests/core/test_parser.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/core/test_parser.py` 끝에 추가:

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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -k factory -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.parser.factory'`

- [ ] **Step 3: 최소 구현**

`core/parser/factory.py`:

```python
from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser
from core.parser.pdf_parser import PdfParser


class ParserFactory:
    """파일 확장자로 DocumentParser 구현체를 선택한다 (ADR-0013 D3)."""

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
```

`core/parser/__init__.py` 를 아래로 교체:

```python
from core.parser.base import DocumentParser
from core.parser.factory import ParserFactory
from core.parser.markdown_parser import MarkdownParser
from core.parser.pdf_parser import PdfParser

__all__ = ["DocumentParser", "MarkdownParser", "PdfParser", "ParserFactory"]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -v`
Expected: PASS (전체 통과)

- [ ] **Step 5: Commit**

```bash
git add core/parser/factory.py core/parser/__init__.py tests/core/test_parser.py
git commit -m "feat(parser): add ParserFactory ext->parser dispatch (ADR-0013 D3)"
```

---

## Task 5: MultiFormatLoader

**Files:**
- Create: `core/loader/multi_format_loader.py`
- Modify: `core/loader/__init__.py`
- Test: `tests/core/test_multi_format_loader.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/core/test_multi_format_loader.py`:

```python
import pytest

from core.loader.base import DocumentLoader
from core.loader.multi_format_loader import MultiFormatLoader


def test_implements_abc():
    assert issubclass(MultiFormatLoader, DocumentLoader)


def test_loads_markdown(tmp_path):
    (tmp_path / "a.md").write_text("# A\nhello", encoding="utf-8")
    docs = MultiFormatLoader().load(str(tmp_path))
    assert [d.source for d in docs] == ["a.md"]
    assert docs[0].text == "# A\nhello"


def test_ignores_unsupported_extension(tmp_path):
    (tmp_path / "a.md").write_text("md", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nope", encoding="utf-8")
    docs = MultiFormatLoader().load(str(tmp_path))
    assert [d.source for d in docs] == ["a.md"]


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
    docs = MultiFormatLoader().load(str(tmp_path))
    by_source = {d.source: d.text for d in docs}
    assert by_source["a.md"] == "md body"
    assert "PdfBody" in by_source["b.pdf"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/test_multi_format_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.loader.multi_format_loader'`

- [ ] **Step 3: 최소 구현**

`core/loader/multi_format_loader.py` (기존 `MarkdownLoader`의 워킹·path 로직을 따르되 확장자 필터를 factory 기반으로 일반화):

```python
import os

from core.loader.base import DocumentLoader
from core.models import Document
from core.parser.factory import ParserFactory


class MultiFormatLoader(DocumentLoader):
    """디렉토리를 워킹하며 지원 포맷 파일을 파서로 Markdown 문자열화한다.

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
                docs.append(Document(text=text, source=rel, metadata={"path": doc_path}))
        return docs
```

`core/loader/__init__.py` 를 아래로 교체:

```python
from core.loader.base import DocumentLoader
from core.loader.markdown_loader import MarkdownLoader
from core.loader.multi_format_loader import MultiFormatLoader

__all__ = ["DocumentLoader", "MarkdownLoader", "MultiFormatLoader"]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/test_multi_format_loader.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add core/loader/multi_format_loader.py core/loader/__init__.py tests/core/test_multi_format_loader.py
git commit -m "feat(loader): add MultiFormatLoader using ParserFactory (ADR-0013 D1)"
```

---

## Task 6: 주입 지점 교체 + 회귀 확인

**Files:**
- Modify: `app/ingestion/indexer.py`

- [ ] **Step 1: loader import 교체**

`app/ingestion/indexer.py:8` 의:

```python
from core.loader import MarkdownLoader
```

를:

```python
from core.loader import MultiFormatLoader
```

- [ ] **Step 2: loader 인스턴스 교체**

`app/ingestion/indexer.py:18` 의:

```python
    loader = MarkdownLoader(base_path=base_path)
```

를:

```python
    loader = MultiFormatLoader(base_path=base_path)
```

- [ ] **Step 3: 전체 테스트 실행 (회귀 확인)**

Run: `.venv/bin/python -m pytest tests/core/ -q`
Expected: PASS — 기존 `test_loader.py`(MarkdownLoader 보존) 포함 전부 통과. `MultiFormatLoader`가 기존 md를 동일하게 처리하므로 회귀 없음.

- [ ] **Step 4: Commit**

```bash
git add app/ingestion/indexer.py
git commit -m "feat(ingestion): wire MultiFormatLoader into build_index (ADR-0013)"
```

---

## Task 7: ADR 상태 갱신 + 인덱스 재생성

**Files:**
- Modify: `docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md`
- Modify (자동): `docs/superpowers/decisions/README.md`

- [ ] **Step 1: ADR-0013 Status 줄 교체**

`docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md:3` 의:

```markdown
> **Status**: 🟡 보류 — 미구현 (현재 Markdown 인제스천만)
```

를:

```markdown
> **Status**: 🟢 적용완료 — D1~D3(파서 격리 + PdfParser) 적용. D4(원본 bytea 보관)·D5(enrichment)는 후속.
```

- [ ] **Step 2: ADR 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성 (ADR-0013 상태가 🟢 적용완료로 바뀜)

- [ ] **Step 3: 변경 확인**

Run: `git diff --stat docs/superpowers/decisions/`
Expected: ADR-0013 + README.md 2개 파일 변경

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0013 D1~D3 적용완료 — PDF 인제스천 파서 격리"
```

---

## 최종 검증 (전체 DoD)

- [ ] **전체 테스트**: `.venv/bin/python -m pytest tests/ -q` → 전부 PASS
- [ ] **lint**: `.venv/bin/ruff check core/parser core/loader app/ingestion/indexer.py` → 통과
- [ ] eval 회귀: loader 교체는 기존 md 인덱싱 결과를 바꾸지 않음(파서 pass-through). 기존 코퍼스가 md뿐이면 점수 불변. (PDF를 코퍼스에 추가하는 것은 별도 작업.)
