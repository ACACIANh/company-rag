# 인제스천 기획 축소 (다중 포맷·원본 보관·다운로드 철회) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ADR-0013이 도입한 다중 포맷(PDF) 인제스천·원본 보관(document_originals)·권한검증 다운로드를 전부 철회하고, 인제스천을 Markdown 단일 포맷으로 복귀한다. 파서 추상화(DocumentParser ABC)는 보존한다.

**Architecture:** 활성 로더를 ADR-0013 이전부터 잔존하는 `MarkdownLoader`로 되돌리고 `MultiFormatLoader`를 제거한다. `core/parser/` 패키지(DocumentParser ABC·MarkdownParser·ParserFactory)는 미연결 추상화로 **보존**(CLAUDE.md 규칙 5, `feedback_prefers_abstraction`)하되 PDF 구현·`pypdf` 의존성·factory의 `.pdf` 분기만 제거한다. `core/document_original/` 패키지·다운로드 엔드포인트·`Document.raw/mime`는 완전히 제거한다. 각 커밋은 테스트 스위트를 green으로 유지하도록 순서를 잡는다.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, pytest. 작업 디렉토리 `backend/`, 인터프리터 `.venv/bin/python`.

---

## 사전 확인된 사실 (작업 전제)

- 시드/코퍼스에 `.pdf` 파일 **0건** (`find . -name '*.pdf'` 무결과) → 단일 포맷 복귀로 인덱싱 손실 없음.
- `Document.raw`/`Document.mime` 소비처는 전부 제거 대상(`multi_format_loader.py`, `document_original/postgres_store.py`, `indexer.py`, `documents.py`) 안에만 존재 → 제거 후 dead.
- `tests/core/test_loader.py`가 복귀 대상 `MarkdownLoader`(base_path 포함)를 이미 망라 테스트.
- 업로드 엔드포인트는 원래 없음. 프론트엔드(web/)에 다운로드/업로드 UI 흔적 없음.
- `document_originals` 테이블은 마이그레이션 파일 없이 `ensure_table()` 인라인 생성 → 코드 제거 시 더 이상 생성/참조 안 됨. 기존 배포 DB의 잔존 테이블은 운영상 수동 `DROP TABLE document_originals`(선택, 코드 변경 아님).

## File Structure (최종 상태)

**제거**
- `core/loader/multi_format_loader.py`, `tests/core/test_multi_format_loader.py`
- `core/document_original/` (base.py, postgres_store.py, __init__.py), `tests/core/test_document_original_store.py`
- `core/parser/pdf_parser.py`
- `app/api/documents.py`, `tests/app/api/test_documents_api.py`

**수정**
- `app/ingestion/indexer.py` — 로더를 `MarkdownLoader`로, original_store 제거
- `core/indexer/indexer.py` — `original_store` 파라미터·저장 루프 제거
- `core/loader/__init__.py` — `MultiFormatLoader` export 제거
- `core/parser/factory.py`, `core/parser/__init__.py` — PdfParser/`.pdf` 제거
- `core/models.py` — `Document.raw`/`Document.mime` 제거
- `app/api/chat.py` — original_store·documents_router 와이어링 제거
- `app/api/deps.py` — `get_original_store` 제거
- `pyproject.toml` — `pypdf` 의존성 제거
- `tests/core/test_indexer.py`, `tests/core/test_parser.py` — 제거된 기능 테스트 삭제

**보존 (미연결 추상화, 규칙 5)**
- `core/parser/base.py` (DocumentParser ABC), `core/parser/markdown_parser.py` (MarkdownParser), `core/parser/factory.py` (ParserFactory, `.md`만)

**신규**
- `docs/superpowers/decisions/ADR-0019-scope-down-ingestion.md`

---

## Task 0: 작업 브랜치 생성

main에서 직접 작업하지 않는다 (CLAUDE.md 커밋 규칙).

- [ ] **Step 1: 브랜치 생성**

```bash
cd /Users/acacian/vscode/company-rag/backend
git checkout -b feat/scope-down-ingestion
```

- [ ] **Step 2: 기준 스위트 green 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS (현재 318개대 통과 상태가 기준).

---

## Task 1: 다운로드 API + app 와이어링 제거

**Files:**
- Delete: `app/api/documents.py`, `tests/app/api/test_documents_api.py`
- Modify: `app/api/chat.py`, `app/api/deps.py`

- [ ] **Step 1: 다운로드 엔드포인트·테스트 삭제**

```bash
git rm app/api/documents.py tests/app/api/test_documents_api.py
```

- [ ] **Step 2: `app/api/deps.py`에서 original_store 의존성 제거**

`core/document_original/base.py` import(라인 10)와 `get_original_store`(라인 33-34)를 삭제한다.

삭제할 import 줄:
```python
from core.document_original.base import DocumentOriginalStore
```
삭제할 함수:
```python
def get_original_store(request: Request) -> DocumentOriginalStore:
    return request.app.state.original_store
```

- [ ] **Step 3: `app/api/chat.py`에서 original_store·documents_router 제거**

다음 4곳을 삭제한다.
- import (라인 28): `from core.document_original.postgres_store import PostgresDocumentOriginalStore`
- import (라인 36): `from app.api.documents import router as documents_router`
- lifespan (라인 73-74):
  ```python
  original_store = PostgresDocumentOriginalStore(pool)
  await original_store.ensure_table()
  ```
- app.state (라인 98): `app.state.original_store = original_store`
- 라우터 등록 (라인 119): `app.include_router(documents_router)`

- [ ] **Step 4: 스위트 green 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. (download/deps 테스트 삭제됨, 나머지 영향 없음. `core/document_original`·`MultiFormatLoader`는 아직 존재하므로 import 에러 없음.)

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "refactor(api): remove document download endpoint + original_store wiring (revert ADR-0013)"
```

---

## Task 2: 인제스천 로더 복귀 + Indexer original_store 제거

**Files:**
- Modify: `app/ingestion/indexer.py`, `core/indexer/indexer.py`, `tests/core/test_indexer.py`

- [ ] **Step 1: `app/ingestion/indexer.py` 로더를 MarkdownLoader로 복귀**

파일 전체를 아래로 교체한다 (MultiFormatLoader → MarkdownLoader, original_store 와이어링 제거).

```python
import os

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.indexer.indexer import Indexer
from core.loader import MarkdownLoader
from core.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


async def build_index(docs_path: str) -> None:
    config = load_config()
    # 코퍼스 루트 디렉토리명이 곧 최상위 폴더 path (docs/company → /company).
    base_path = "/" + os.path.basename(docs_path.rstrip("/"))
    loader = MarkdownLoader(base_path=base_path)
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn)
    store = create_vector_store(config, pool)

    await Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
    ).index(docs_path)

    await pool.close()
```

- [ ] **Step 2: `core/indexer/indexer.py`에서 original_store 제거**

파일 전체를 아래로 교체한다.

```python
from core.chunker.base import Chunker
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
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store

    async def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        await self._store.add(chunks, embeddings)
        return len(chunks)
```

- [ ] **Step 3: `tests/core/test_indexer.py`에서 original_store 테스트 제거**

라인 78~120(파일 끝)을 통째로 삭제한다 — `@pytest.mark.asyncio` 데코레이터가 붙은 `test_index_saves_originals_when_store_given`과 `test_index_without_original_store_does_not_fail` 두 함수 블록(각자의 로컬 import 포함). 라인 1~76(상단 import + 나머지 4개 테스트)은 그대로 둔다. 삭제 후 파일 마지막 테스트는 `test_indexer_skips_fga_when_no_fga_client`(라인 64-75)가 된다.

- [ ] **Step 4: indexer 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/test_indexer.py -q`
Expected: PASS (original_store 테스트 제거됨, 핵심 인덱싱 테스트 통과).

- [ ] **Step 5: 스위트 green 확인 + 커밋**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

```bash
git add -A
git commit -m "refactor(ingestion): revert loader to MarkdownLoader, drop Indexer original_store"
```

---

## Task 3: document_original 패키지 제거

이 시점에 `core/document_original/`은 어디서도 참조되지 않는다 (Task 1·2에서 모든 소비처 제거).

**Files:**
- Delete: `core/document_original/base.py`, `core/document_original/postgres_store.py`, `core/document_original/__init__.py`, `tests/core/test_document_original_store.py`

- [ ] **Step 1: 패키지·테스트 삭제**

```bash
git rm -r core/document_original tests/core/test_document_original_store.py
```

- [ ] **Step 2: 잔존 참조 없음 확인**

Run: `grep -rn "document_original\|OriginalRecord\|DocumentOriginalStore\|original_store" --include="*.py" . | grep -v "/.venv/"`
Expected: 무결과 (출력 없음).

- [ ] **Step 3: 스위트 green 확인 + 커밋**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

```bash
git add -A
git commit -m "refactor(core): remove document_original package (original storage retired)"
```

---

## Task 4: MultiFormatLoader 제거 (활성 로더는 MarkdownLoader)

**Files:**
- Delete: `core/loader/multi_format_loader.py`, `tests/core/test_multi_format_loader.py`
- Modify: `core/loader/__init__.py`

- [ ] **Step 1: MultiFormatLoader·테스트 삭제**

```bash
git rm core/loader/multi_format_loader.py tests/core/test_multi_format_loader.py
```

- [ ] **Step 2: `core/loader/__init__.py`에서 export 제거**

파일 전체를 아래로 교체한다.

```python
from core.loader.base import DocumentLoader
from core.loader.markdown_loader import MarkdownLoader

__all__ = ["DocumentLoader", "MarkdownLoader"]
```

- [ ] **Step 3: 잔존 참조 없음 확인**

Run: `grep -rn "MultiFormatLoader" --include="*.py" . | grep -v "/.venv/"`
Expected: 무결과.

- [ ] **Step 4: loader 테스트 + 스위트 green 확인 + 커밋**

Run: `.venv/bin/python -m pytest tests/core/test_loader.py -q`
Expected: PASS (MarkdownLoader 망라 테스트).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

```bash
git add -A
git commit -m "refactor(loader): remove MultiFormatLoader, MarkdownLoader is the sole loader"
```

---

## Task 5: 파서를 Markdown 단일로 축소 (ABC·factory 보존)

PdfParser·pypdf 의존만 제거하고 DocumentParser ABC·MarkdownParser·ParserFactory(`.md`)는 보존한다.

**Files:**
- Delete: `core/parser/pdf_parser.py`
- Modify: `core/parser/factory.py`, `core/parser/__init__.py`, `tests/core/test_parser.py`

- [ ] **Step 1: PdfParser 삭제**

```bash
git rm core/parser/pdf_parser.py
```

- [ ] **Step 2: `core/parser/factory.py`에서 `.pdf` 제거**

파일 전체를 아래로 교체한다.

```python
from core.parser.base import DocumentParser
from core.parser.markdown_parser import MarkdownParser


class ParserFactory:
    """파일 확장자로 DocumentParser 구현체를 선택한다 (현재 Markdown 단일)."""

    _MIME = {".md": "text/markdown"}

    def __init__(self) -> None:
        self._parsers: dict[str, DocumentParser] = {
            ".md": MarkdownParser(),
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

- [ ] **Step 3: `core/parser/__init__.py`에서 PdfParser export 제거**

파일 전체를 아래로 교체한다.

```python
from core.parser.base import DocumentParser
from core.parser.factory import ParserFactory
from core.parser.markdown_parser import MarkdownParser

__all__ = ["DocumentParser", "MarkdownParser", "ParserFactory"]
```

- [ ] **Step 4: `tests/core/test_parser.py`를 Markdown 단일 상태로 교체**

파일 전체를 아래로 교체한다 (PDF 헬퍼·PDF 테스트 4개 제거, factory 단언을 `.md` 단일로 수정).

```python
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
```

- [ ] **Step 5: parser 테스트 + pypdf 미참조 확인**

Run: `.venv/bin/python -m pytest tests/core/test_parser.py -q`
Expected: PASS.

Run: `grep -rn "pypdf\|PdfParser" --include="*.py" . | grep -v "/.venv/"`
Expected: 무결과.

- [ ] **Step 6: 스위트 green 확인 + 커밋**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

```bash
git add -A
git commit -m "refactor(parser): collapse to Markdown-only, keep DocumentParser ABC (ADR-0013 D1 seam retained)"
```

---

## Task 6: Document.raw/mime 제거 + pypdf 의존성 제거

Task 1~5로 raw/mime 소비처가 모두 사라졌다 (사전 확인됨).

**Files:**
- Modify: `core/models.py`, `pyproject.toml`

- [ ] **Step 1: 잔존 소비처 없음 재확인**

Run: `grep -rn "\.raw\b\|\.mime\b\|\braw=\|\bmime=" --include="*.py" . | grep -v "/.venv/" | grep -v "core/models.py"`
Expected: 무결과 (테스트 포함 어디서도 Document.raw/mime를 쓰지 않음).

- [ ] **Step 2: `core/models.py`의 Document에서 raw/mime 필드 제거**

`Document` 데이터클래스를 아래로 교체한다 (다른 데이터클래스는 그대로).

```python
@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)
```

- [ ] **Step 3: `pyproject.toml`에서 pypdf 의존성 제거**

라인 31 `    "pypdf>=4.0,<6",`를 삭제한다.

- [ ] **Step 4: 스위트 green 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: (선택) pypdf 제거가 환경에 반영되는지 확인**

pypdf는 이제 import되지 않으므로 설치 잔존 여부는 테스트에 무관하다. 의존성 lock을 쓰는 경우에만 재동기화한다. (이 저장소는 `.venv` 직접 관리이므로 추가 조치 불필요.)

- [ ] **Step 6: 커밋**

```bash
git add -A
git commit -m "refactor(core): drop Document.raw/mime and pypdf dependency (no remaining consumers)"
```

---

## Task 7: DoD — 전체 스위트 + eval 회귀 확인

- [ ] **Step 1: 전체 단위 테스트**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. 삭제된 테스트 수만큼 총계가 줄어든 것 외 실패 0.

- [ ] **Step 2: eval 회귀 점수 (env 가용 시)**

Run: `.venv/bin/python -m tests.eval.runner`
Expected: 코퍼스 내용 불변(전부 .md, 인덱싱 경로만 로더 교체)이므로 검색 품질 회귀 없음. 점수 하락 시 원인 명시. (외부 키/서비스 미가용이면 스킵하고 그 사실을 기록.)

- [ ] **Step 3: import 무결성 스모크 확인**

Run: `.venv/bin/python -c "import app.api.chat; import app.ingestion.indexer; import core.parser; import core.loader; print('ok')"`
Expected: `ok` 출력 (제거 후 import 깨짐 없음).

---

## Task 8: 결정 기록 — ADR-0019 작성 + ADR-0013 대체 + 인덱스/메모리 갱신

**Files:**
- Create: `docs/superpowers/decisions/ADR-0019-scope-down-ingestion.md`
- Modify: `docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md`
- Modify (memory): `/Users/acacian/.claude/projects/-Users-acacian-vscode-company-rag/memory/project_multiformat_ingestion.md` + `MEMORY.md`

- [ ] **Step 1: ADR-0019 작성**

아래 내용으로 `docs/superpowers/decisions/ADR-0019-scope-down-ingestion.md`를 생성한다.

```markdown
# ADR-0019: 기획 축소 — 다중 포맷·원본 보관·다운로드 철회, Markdown 단일 인제스천 복귀

> **Status**: 🟢 적용완료

**Date**: 2026-06-02
**Context**: [ADR-0013](ADR-0013-multi-format-ingestion.md)은 다중 포맷(PDF) 인제스천 + 원본 bytea 보관(`document_originals`) + 권한검증 다운로드를 도입했다. 제품 범위를 RAG 검색·권한 게이트 핵심으로 좁히기 위해 이 기획을 철회한다: 파일 업로드/다운로드 전부 제거, 인제스천을 Markdown 단일 포맷으로 복귀. 단, 파서 추상화(DocumentParser ABC)는 학습 목적·향후 재확장 여지로 보존한다(CLAUDE.md 규칙 5, [[feedback_prefers_abstraction]]).

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| ADR-0013 유지 (다중포맷 + 원본보관 + 다운로드) | 기능 풍부. 그러나 현 범위 밖, 코드 표면적·외부 의존(pypdf)·운영(bytea 테이블) 유지비 |
| Markdown 단일 인제스천 복귀, 파서 ABC만 보존 | 표면적 최소화·핵심 집중. PDF·원본·다운로드 제거. 파서 seam은 남겨 재확장 여지 유지 |

## Decision

**선택: Markdown 단일 인제스천으로 복귀하고 파서 ABC를 보존한다.**

- 활성 로더를 `MarkdownLoader`(ADR-0013 이전 구현, 잔존)로 복귀. `MultiFormatLoader` 제거.
- `core/parser/`의 DocumentParser ABC·MarkdownParser·ParserFactory(`.md`)는 **보존**(미연결 추상화, 규칙 5). `PdfParser`·`pypdf`·factory의 `.pdf` 분기 제거.
- `core/document_original/`(ABC·Postgres 구현·`document_originals` 테이블) 전부 제거. `Indexer`의 original_store 경로·`Document.raw`/`mime` 제거.
- 다운로드 엔드포인트(`app/api/documents.py`)·라우터 등록·`get_original_store` 의존성 제거.
- 기존 배포 DB의 `document_originals` 테이블은 코드가 더 이상 생성/참조하지 않음 → 운영상 수동 `DROP TABLE document_originals`(선택, 코드 변경 아님).

## Rationale

- **범위 집중**: 검색 품질·권한 게이트(ADR-0016~0018 방향)에 자원을 모은다. 업로드/다운로드는 현 단계 비핵심.
- **추상화 보존**: 파서 ABC를 남겨 향후 포맷 재확장 seam을 유지(규칙 5, [[feedback_prefers_abstraction]]). 구체 PDF 구현·외부 의존성만 제거해 설치·표면적 부담을 줄인다.
- **무손실**: 시드 코퍼스가 전부 `.md`라 단일 포맷 복귀로 인덱싱 손실 없음(검증: `find . -name '*.pdf'` 0건).

## 영향받는 결정

- [ADR-0013](ADR-0013-multi-format-ingestion.md) — 🟣 대체됨. D1~D5 + 다운로드 철회. 파서 격리(D1)의 ABC만 보존.
- [ADR-0016](ADR-0016-identity-risk-sql-gate.md)~[ADR-0018](ADR-0018-decision-audit-log.md) — 본 축소 후 에이전틱 SQL 도구 작업에 착수.
```

- [ ] **Step 2: ADR-0013 Status 배지를 대체됨으로 변경**

`docs/superpowers/decisions/ADR-0013-multi-format-ingestion.md`의 첫 Status 줄(라인 3)을 아래로 교체한다.

변경 전:
```markdown
> **Status**: 🟢 적용완료 — D1~D5 적용 (PDF 파서 격리 + 원본 bytea 보관 + 권한검증 다운로드). 페이지 단위 역추적·S3 이전은 후속.
```
변경 후:
```markdown
> **Status**: 🟣 대체됨 → [ADR-0019](ADR-0019-scope-down-ingestion.md) — 다중 포맷·원본 보관·다운로드 철회, Markdown 단일 인제스천으로 복귀. 파서 ABC만 보존.
```

- [ ] **Step 3: ADR 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `생성 완료: .../README.md (19 ADR)`. README에 0019행 추가 + 0013이 🟣 대체됨으로 표시.

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/decisions/
git commit -m "docs(adr): ADR-0019 scope-down ingestion, supersede ADR-0013"
```

- [ ] **Step 5: 메모리 갱신**

`memory/project_multiformat_ingestion.md` 본문을 "ADR-0013 D1~D4+다운로드 완료" → "ADR-0019로 축소 철회(다중포맷·원본·다운로드 제거, MarkdownLoader 복귀, 파서 ABC 보존)"로 갱신하고, `MEMORY.md`의 해당 한 줄 hook도 맞춘다. (코드가 아닌 메모리 파일이므로 커밋 대상 아님.)

---

## 실행 후 (PR)

CLAUDE.md Phase 워크플로우대로, 작업 완료 후 PR을 생성한다 (description에 본 계획의 Task를 DoD 체크리스트로). **사용자가 명시 요청할 때만** push/PR한다.

```bash
git push -u origin feat/scope-down-ingestion
```
