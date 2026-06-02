# ADR-0013: 다중 포맷 문서 인제스천 — 파서 격리 + 통일 중간표현(Markdown)

> **Status**: 🟣 대체됨 → [ADR-0019](ADR-0019-scope-down-ingestion.md) — 다중 포맷·원본 보관·다운로드 철회, Markdown 단일 인제스천으로 복귀. 파서 ABC만 보존.

> 상태: **제안됨(Proposed)** / 작성일: 2026-06-01 / 관련: 역기획서 §3, §7.6, §7.1, §7.3

---

## 1. 맥락 (Context)

- **현행**: Markdown만 인제스천. `MarkdownLoader.load()` → `FixedSizeChunker.chunk(size=500, overlap=50)` → `Embedder.embed_batch()` → `PostgresVectorStore.add()` (§7.6). 역기획서 §3 Non-Goals에 "문서 포맷 다양화 — 현재 Markdown 인제스천만"으로 명시되어 있음.
- **요구**: PDF 등 비-Markdown 문서도 검색 대상에 포함. 단, 향후 docx/html/xlsx 등으로 **확장 가능**해야 함.
- **위험**: 포맷별 처리 로직이 청킹·임베딩·검색 단계에 스며들면 포맷을 추가할 때마다 파이프라인 전체가 흔들림.
- **부가 요구**: 검색은 통일 포맷으로 하되, **원본 파일은 증빙·다운로드용으로 보관**해야 함. AI가 만든 파생 데이터(enrichment)도 붙이고 싶음.

---

## 2. 결정 (Decision)

### D1. 파서 단계만 포맷에 의존, 이후는 포맷 무관

파이프라인을 다음 형태로 고정한다.

```
원본(pdf/docx/html/xlsx...)
  → 포맷별 파서        (여기만 포맷에 의존)
  → 통일 중간표현(Markdown)  (여기서부터 포맷 무관)
  → [enrichment]
  → 청킹
  → 임베딩
```

포맷 의존 코드는 **파서 단계에만 격리**한다. 청킹 이후 단계는 단일 표현(Markdown 문자열) 하나만 다룬다.

### D2. 통일 중간표현 = Markdown

- 제목 계층(`#`)·표·리스트가 보존되어 기존 `FixedSizeChunker`와 **그대로 호환**된다.
- 기존 `MarkdownLoader`는 "md → md" 통과(pass-through) 파서로 흡수한다(별도 분기 불필요).

### D3. `DocumentParser` ABC + Factory (확장점)

- 기존 `core/`의 ABC + Factory 패턴을 따른다(§7.1, §7.3과 일관).
- 확장자/MIME로 파서를 선택한다.
- **PDF 파서를 첫 구현체**로 한다. 새 포맷 추가 = 파서 한 개 등록(다른 레이어 무수정).
- PDF 파서 **내부의 라이브러리 선택은 ABC 뒤에 숨긴 구현 디테일**이며 이 ADR에서 확정하지 않는다(§6 후속).

### D4. 원본 파일은 PostgreSQL `bytea` 보관

- 원본은 **절대 변형하지 않는다**(증빙·다운로드용). 통일표현(Markdown)에서 원본을 역복원하는 것은 불가능으로 간주한다(파싱은 비가역 변환).
- 청크 메타데이터에 **원본 식별자 + 페이지/위치 정보**를 기록해 청크 → 원본 역추적이 가능하게 한다.

### D5. enrichment는 파생 데이터로 분리 저장

- 원본·통일표현을 건드리지 않고 **별도 컬럼/테이블**에 저장한다.
- **인제스천(배치) 시점에 생성**한다(검색 시점 생성 금지 — 지연·비용).
- 생성에 쓴 **모델·프롬프트 버전을 함께 기록**해 재생성 가능하게 한다.
- **초기 범위는 최소**(문서/섹션 요약 1종)로 한다. 그 외는 후속(§6).

---

## 3. 레이어 / 구현 매핑 (제안)

| 책임 | 위치(제안) | 비고 |
|------|-----------|------|
| `DocumentParser` (ABC: `parse(raw) -> Markdown`) | `core/parser/base.py` | LangGraph 불가지, §7.1 준수 |
| `ParserFactory` (확장자/MIME → 파서) | `core/parser/factory.py` | 기존 Factory 패턴 일관 |
| `MarkdownParser` (md → md 통과) | `core/parser/markdown_parser.py` (기존 `core/loader/markdown_loader.py` 흡수) | 동작 동일 |
| `PdfParser` (pdf → md) | `core/parser/adapters/pdf_parser.py` | 첫 신규 구현체 |
| enrichment 생성기 | `core/enrich/` | `LLMClient` 재사용, 배치 호출 |

> 경로는 현행 `core/` 도메인 폴더 패턴(`core/loader`·`core/chunker`·`core/embedder`·`core/reranker` 등 최상위 단위)에 맞춘 **제안**이며 구현 시 최종 확정. 미연결 어댑터·구현체는 CLAUDE.md 규칙 5에 따라 삭제하지 않음.

---

## 4. 데이터 모델 (실제 구현)

> 최초 제안은 documents에 원본+content를 통합했으나, 실제 `documents`는 청크 테이블(pgvector)이라
> 원본은 신규 `document_originals` 테이블에 분리 보관한다.

```
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

- 원본 다운로드는 `GET /documents/download?document_id=...` 로 제공하며, 검색과 동일한 OpenFGA `get_readable_folders` 정확 매칭으로 권한을 재검증한다(§5).

---

## 5. 영향 (Consequences)

**긍정**
- 포맷 추가가 파서 1개로 국소화. 청킹·임베딩·검색·권한 로직 무수정.
- 원본 보관으로 "출처 보기 / 원본 다운로드" 제공 가능.
- 기존 §7.1 레이어 경계·ABC+Factory 원칙을 그대로 유지.

**부정 / 비용**
- `bytea` 보관으로 DB 용량·백업 부담 증가. **대규모로 가면 오브젝트 스토리지(예: S3/MinIO) 이전이 필요**해질 수 있음(현 규모에서는 허용).
- enrichment 생성으로 인제스천 시간·토큰 비용 증가(NFR-10 비용 가시성과 연동해 모니터링).
- PDF 파싱 품질 편차 — 표/이미지가 깨질 수 있음(§6 후속에서 보강).

**주의 (권한 경계와의 연결)** ★
- 검색은 이미 권한 pre-filter가 적용되지만(NFR-1), **원본 다운로드 경로에도 동일한 OpenFGA 폴더 권한 재검증이 반드시 적용**되어야 한다. 그렇지 않으면 검색 경계를 우회하는 유출 경로가 생긴다. → 다운로드 API 설계 시 별도 점검.

---

## 6. 비목표 / 후속 (이 ADR 범위 밖)

- **HWP / HWPX** 등 한국 포맷: 파서 추가로 흡수 가능하나 라이브러리 생태계가 빈약해 별도 검토 필요. 현 범위 외.
- **구조 인지 청킹**: 현재는 `FixedSizeChunker` 유지. Markdown 헤더 기반 청킹은 후속.
- **PDF 파서 라이브러리 확정**: ABC 뒤 구현 디테일로 후속 결정.
- **enrichment 고도화**: 가상 질문(HyDE), 맥락 헤더(contextual retrieval), 표 캡션 등은 요약 1종 안정화 후 추가.
- **bytea → 오브젝트 스토리지 이전**: 용량 임계 도달 시 재검토(§5 부정 항목).

---

## 7. 대안 검토 (요약)

| 대안 | 기각 사유 |
|------|----------|
| 통일표현을 plain text로 | 표·계층 손실 → 구조 기반 검색·청킹 불가 |
| 통일표현을 구조화 JSON(element 트리)으로 | 유연하나 기존 청커·파이프라인 대폭 변경 필요. "딥하게 안 간다" 방침과 상충. (계층 인덱싱이 핵심 요구가 되면 재검토) |
| 원본을 보관하지 않음 | 출처/다운로드/증빙 불가 |
| 원본을 오브젝트 스토리지에 보관 | 혼자 운영 규모엔 인프라 과함. 임계 도달 시 이전(§6) |
