# 다중 포맷 문서 인제스천 (PDF) — 파서 격리 계층 설계

> 관련 ADR: [ADR-0013](../decisions/ADR-0013-multi-format-ingestion.md)
> 범위: ADR-0013의 **D1~D3만** 구현. D4(원본 bytea 보관)·D5(enrichment)는 후속 PR.
> 작성일: 2026-06-02

---

## 1. 목표

현재 Markdown만 인제스천하는 파이프라인에 PDF를 추가한다. 단, 향후 docx/html 등으로 확장 가능하도록 **포맷 의존 코드를 파서 단계에만 격리**한다(ADR-0013 D1).

**Non-goals (이번 범위 밖)**
- D4: 원본 파일 `bytea` 보관 — DB 스키마 변경 필요, 후속 PR
- D5: enrichment(요약 등 파생 데이터) — DB 스키마 변경 필요, 후속 PR
- PDF 표/이미지 구조 보존 — `pypdf` 텍스트 추출 수준에서 시작(ADR-0013 §6 후속)

## 2. 결정 사항 (확정)

| 항목 | 결정 | 근거 |
|------|------|------|
| PDF 라이브러리 | `pypdf` | 순수 파이썬·경량·BSD 라이선스. ParserFactory 뒤에 숨으므로 후속 교체 가능(ADR-0013 D3) |
| loader 통합 | 신규 `MultiFormatLoader` | 디렉토리 워킹+path 메타는 loader 책임, raw→markdown은 parser 책임으로 분리. 기존 `MarkdownLoader` 보존(CLAUDE.md 규칙5) |

## 3. 아키텍처

```
원본(.md / .pdf)
  → MultiFormatLoader        (디렉토리 워킹 + path 메타 + raw bytes 읽기)
  → ParserFactory.get_parser(ext)
  → DocumentParser.parse(raw) -> str(markdown)   (여기만 포맷 의존)
  → Document(text, source, metadata={path})
  → [기존] Chunker → Embedder → VectorStore       (무수정)
```

### 3.1 파서 계층 (신규 `core/parser/`)

기존 `core/`의 ABC + Factory 패턴(reranker/embedder/vector_store)을 그대로 따른다. `core/`는 LangGraph 불가지(CLAUDE.md 레이어 경계 준수).

| 파일 | 책임 | 인터페이스 |
|------|------|-----------|
| `core/parser/base.py` | `DocumentParser` ABC | `parse(raw: bytes) -> str` (markdown 문자열 반환) |
| `core/parser/factory.py` | `ParserFactory` | `get_parser(ext: str) -> DocumentParser`. 미지원 확장자는 `ValueError` |
| `core/parser/markdown_parser.py` | `MarkdownParser` | `raw.decode("utf-8")` pass-through (ADR-0013 D2) |
| `core/parser/pdf_parser.py` | `PdfParser` | `pypdf.PdfReader`로 페이지별 `extract_text()` 결과를 개행으로 연결 |

- `ParserFactory`는 `{".md": MarkdownParser, ".pdf": PdfParser}` 매핑을 보유. 확장자 비교는 소문자 정규화.

### 3.2 MultiFormatLoader (신규 `core/loader/multi_format_loader.py`)

- 생성자 시그니처는 기존 `MarkdownLoader`와 동일: `__init__(self, base_path: str = "")`.
- `load(path)` 로직:
  - 기존 `MarkdownLoader`의 `os.walk` + 상대경로 → `doc_path` 메타 생성 로직을 **그대로** 따른다.
  - 확장자 필터를 `.md` 단일에서 → `ParserFactory`가 지원하는 확장자 집합으로 확장.
  - 각 파일을 **bytes로 읽어**(`open(full, "rb")`) `factory.get_parser(ext).parse(raw)` → text → `Document(text=text, source=rel, metadata={"path": doc_path})`.
  - 지원하지 않는 확장자 파일은 기존처럼 조용히 건너뛴다(현행 `.md` 외 무시 동작과 동일).

### 3.3 주입 지점 변경

- `app/ingestion/indexer.py`: `MarkdownLoader(base_path=...)` → `MultiFormatLoader(base_path=...)`로 교체. `Indexer`·`build_index` 시그니처 무수정.
- 기존 `MarkdownLoader`는 삭제하지 않고 보존(CLAUDE.md 규칙5).

## 4. 데이터 흐름 / 권한 영향

- `Document.metadata["path"]`는 현행과 동일하게 생성된다 → OpenFGA path-prefix 권한 필터(ADR-0011/0015)에 **영향 없음**.
- 원본 다운로드 경로는 이번 범위에 없음(D4 후속). ADR-0013 §5의 "다운로드 API 권한 재검증"은 D4 PR에서 다룬다.

## 5. 테스트 전략

| 대상 | 테스트 |
|------|--------|
| `MarkdownParser` | bytes → 동일 문자열 decode 확인 |
| `PdfParser` | 작은 샘플 PDF fixture에서 알려진 텍스트 추출 확인 |
| `ParserFactory` | `.md`/`.pdf` 올바른 인스턴스 반환, 대문자 확장자 정규화, 미지원 확장자 `ValueError` |
| `MultiFormatLoader` | md+pdf 혼합 임시 디렉토리에서 두 포맷 모두 `Document`로 로드, `path` 메타 정확성, 미지원 파일 무시 |

- PDF fixture는 테스트 내에서 `pypdf`로 즉석 생성하거나(텍스트 1줄), 작은 고정 PDF를 `tests/` 하위에 둔다. 즉석 생성을 우선 시도한다.

## 6. DoD

1. 위 단위 테스트 추가 — `cd backend && .venv/bin/python -m pytest`
2. eval 회귀 확인: loader 교체가 기존 md 인덱싱 결과를 바꾸지 않음을 확인(점수 하락 없음)
3. 신규 의존성 `pypdf` → `pyproject.toml` 추가, ADR-0013 상태 갱신(🟡 보류 → 🟢 적용완료, "D1~D3 적용, D4/D5 후속" 명시) → `python -m scripts.gen_adr_index`
