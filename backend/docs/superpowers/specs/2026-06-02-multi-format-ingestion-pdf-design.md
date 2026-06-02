# 다중 포맷 문서 인제스천 (PDF) + 원본 보관/다운로드 설계

> 관련 ADR: [ADR-0013](../decisions/ADR-0013-multi-format-ingestion.md)
> 범위: ADR-0013의 **D1~D5 전체** 구현 (파서 격리 + PDF + 원본 bytea 보관 + 다운로드 API).
> 작성일: 2026-06-02

---

## 1. 목표

현재 Markdown만 인제스천하는 파이프라인에 PDF를 추가하고, 검색은 추출 텍스트로 하되 **원본 파일을 증빙·다운로드용으로 보관**한다. 포맷 의존 코드는 파서 단계에만 격리한다(ADR-0013 D1).

**핵심 보안 요구**: 원본 다운로드 경로에도 검색과 **동일한 OpenFGA 폴더 권한 재검증**을 적용한다. 누락 시 검색 경계를 우회하는 유출 경로가 생긴다(ADR-0013 §5).

**Non-goals (이번 범위 밖, 후속)**
- 페이지/위치 단위 청크→원본 역추적 (이번엔 **문서 단위**만)
- PDF 표/이미지 구조 보존 (`pypdf` 텍스트 추출 수준)
- `bytea` → 오브젝트 스토리지 이전 (용량 임계 도달 시)
- enrichment 고도화 (HyDE/맥락 헤더 등)

## 2. 현행 스키마 파악 (ADR-0013 §4 가정과의 차이) ★

코드 확인 결과 ADR-0013 §4가 그린 "documents에 original_file+content 통합" 모델은 **실제와 다르다**:

- `documents` 테이블(`core/vector_store/postgres_store.py`)은 **청크 단위** 테이블이다(`chunk_id` UNIQUE, `content`=청크 텍스트, `embedding`, `path`, `source`).
- 문서 본문의 source of truth는 `document_versions`(ADR-0012)이나, **현재 인제스천(`build_index`)이 이 테이블을 채우지 않는다**(`ensure_table`만 호출됨).

→ 원본은 **신규 `document_originals` 테이블**에 둔다(documents 청크 테이블과 책임 분리). ADR-0013 §4는 이 실제 구조에 맞게 정정한다(구현 시 Task에 포함).

## 3. 결정 사항 (확정)

| 항목 | 결정 | 근거 |
|------|------|------|
| PDF 라이브러리 | `pypdf` | 순수 파이썬·경량·BSD. ParserFactory 뒤 교체 가능(ADR-0013 D3) |
| loader 통합 | 신규 `MultiFormatLoader` | 워킹+path 메타는 loader, raw→markdown은 parser로 분리. `MarkdownLoader` 보존(CLAUDE.md 규칙5) |
| 원본 저장 위치 | 신규 `document_originals` 테이블 (bytea) | 청크 테이블과 분리. 현 규모 bytea 허용(ADR-0013 §5) |
| 다운로드 권한 | `get_readable_folders` 정확 매칭 | 검색 pre-filter(`build_pg_filter`)와 동일 체계 |
| 역추적 단위 | 문서 단위(`document_id`) | 페이지 단위는 청커가 페이지 경계를 알아야 해 후속 |

## 4. 아키텍처

```
원본(.md / .pdf)
  → MultiFormatLoader        (워킹 + path 메타 + raw bytes + mime)
  → ParserFactory.get_parser(ext).parse(raw) -> str(markdown)   (여기만 포맷 의존)
  → Document(text, source, metadata={path}, raw, mime)
  → Indexer
      ├─ [기존] Chunker → Embedder → VectorStore(documents 청크)   무수정
      └─ [신규] DocumentOriginalStore.save(원본 bytea)            original_store 주입 시
```

### 4.1 파서 계층 (신규 `core/parser/`)

기존 `core/` ABC + Factory 패턴(reranker/embedder)을 따른다. `core/`는 LangGraph 불가지.

| 파일 | 책임 | 인터페이스 |
|------|------|-----------|
| `core/parser/base.py` | `DocumentParser` ABC | `parse(raw: bytes) -> str` |
| `core/parser/markdown_parser.py` | `MarkdownParser` | `raw.decode("utf-8")` pass-through (D2) |
| `core/parser/pdf_parser.py` | `PdfParser` | `pypdf`로 페이지 텍스트 추출, `\n\n` 연결 |
| `core/parser/factory.py` | `ParserFactory` | `get_parser(ext)`, `supported_extensions()`, `mime_for(ext)`. 미지원시 `ValueError` |

- `mime_for`: `.md`→`text/markdown`, `.pdf`→`application/pdf`.

### 4.2 MultiFormatLoader (신규 `core/loader/multi_format_loader.py`)

- 생성자: `__init__(self, base_path: str = "")` — `MarkdownLoader`와 동일.
- `load(path)`: 기존 `os.walk` + 상대경로→`doc_path` 메타 로직 유지. 확장자 필터를 factory 지원 집합으로 일반화. 각 파일을 **bytes로 읽어** parser로 text 변환 후 `Document(text, source=rel, metadata={"path": doc_path}, raw=raw, mime=factory.mime_for(ext))`.
- 미지원 확장자는 조용히 skip(현행 동작 유지).

### 4.3 Document 모델 확장 (`core/models.py`)

```python
@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)
    raw: bytes | None = None      # 원본 bytes (D4). loader가 채움
    mime: str | None = None       # 원본 MIME. loader가 채움
```
선택 필드(기본값 있음) → 기존 `MarkdownLoader`·테스트·호출부 무영향.

### 4.4 원본 저장소 (신규 `core/document_original/`)

| 파일 | 책임 |
|------|------|
| `core/document_original/base.py` | `DocumentOriginalStore` ABC: `ensure_table()`, `save(document_id, folder_path, filename, mime, raw)`, `get_latest(document_id) -> OriginalRecord | None` |
| `core/document_original/postgres_store.py` | `document_originals` 테이블 구현 |

- `document_id` = `folder_path + "/" + filename` (path 기반 안정 키, ADR-0012 키 방식과 일관).
- `save`: 원본 SHA-256 계산 → 같은 document_id 최신 버전과 hash 동일하면 skip, 다르면 `version+1` insert.
- `OriginalRecord` dataclass: `document_id, version, folder_path, filename, mime, original_file, content_hash`.

### 4.5 Indexer 확장 (`core/indexer/indexer.py`)

```python
def __init__(self, loader, chunker, embedder, store, original_store=None): ...

async def index(self, path):
    docs = self._loader.load(path)
    if self._original_store is not None:
        for d in docs:
            if d.raw is not None and d.mime is not None:
                fp = d.metadata.get("path", "")
                filename = d.source.rsplit("/", 1)[-1]
                await self._original_store.save(fp + "/" + filename, fp, filename, d.mime, d.raw)
    # 이하 기존 청킹/임베딩/저장 흐름 무수정
```
`original_store=None`이면 기존 동작 그대로 → 기존 `test_indexer.py` 무영향.

### 4.6 다운로드 API (신규 `app/api/documents.py`)

```
GET /documents/download?document_id=<path 기반 키>     (Depends: get_current_user, get_fga_client)
1. folders = await fga_client.get_readable_folders(user["user_id"])
2. rec = await original_store.get_latest(document_id)
3. rec is None  → 404
4. rec.folder_path not in folders  → 404 (존재 노출 방지)
5. StreamingResponse(iter([rec.original_file]), media_type=rec.mime,
       headers={"Content-Disposition": f'attachment; filename="{rec.filename}"'})
```
- 권한은 검색과 **동일한 정확 매칭**(`folder_path in folders`). prefix 확장 없음(private 하위 유출 방지, `build_pg_filter` 주석 근거).
- 라우터는 `app/api/__init__.py`(또는 앱 조립부)에 등록. `original_store`는 app.state로 주입(기존 fga_client 패턴과 동일).

## 5. 권한/보안 영향

- `Document.metadata["path"]`는 현행과 동일 → 검색 권한 pre-filter 무영향.
- 다운로드 경로가 유일한 신규 노출면. §4.6의 4·5단계가 검색과 동일 경계를 강제. 미스매치 시 404로 존재 자체를 숨긴다.

## 6. 테스트 전략

| 대상 | 테스트 |
|------|--------|
| `MarkdownParser`/`PdfParser`/`ParserFactory` | decode pass-through / pdf 텍스트 추출 / 확장자 분기·정규화·`mime_for`·미지원 `ValueError` |
| `MultiFormatLoader` | md+pdf 혼합 로드, `path` 메타, `raw`/`mime` 채워짐, 미지원 skip |
| `DocumentOriginalStore` | save 후 get_latest 일치, 동일 hash 재저장시 version 불변, 변경시 version+1 |
| 다운로드 API | 가시 폴더 통과 200+올바른 mime, 비가시 폴더 404, 없는 문서 404, 미인증 401 |
| 회귀 | `Indexer(original_store=None)` 기존 동작 불변, `MarkdownLoader` 보존 |

- DB 테스트는 기존 `test_vector_store.py`/`test_document_version_store.py`의 픽스처 패턴(실 PG 또는 기존 mock 전략)을 따른다.
- PDF fixture는 `pypdf`로 즉석 생성 우선, 실패 시 고정 샘플 파일 fallback.

## 7. DoD

1. 위 단위/통합 테스트 추가 — `cd backend && .venv/bin/python -m pytest`
2. eval 회귀: loader/Indexer 변경이 기존 md 인덱싱 결과를 바꾸지 않음(점수 하락 없음)
3. 신규 의존성 `pypdf` → `pyproject.toml` 추가
4. **ADR-0013 §4 정정**(실제 `document_originals` 스키마 반영) + Status 갱신(🟡 보류 → 🟢 적용완료) → `python -m scripts.gen_adr_index`
