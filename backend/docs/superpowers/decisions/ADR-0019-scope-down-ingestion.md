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
- **무손실**: 시드 코퍼스가 전부 `.md`라 단일 포맷 복귀로 인덱싱 손실 없음(검증: `find . -name '*.pdf'` 0건). 로더 교체만이고 코퍼스 내용은 불변이라 검색 품질 회귀 요인 없음.

## 검증

- 단위 테스트 전체 통과(353 → 330; 차이 23은 제거된 download·original_store·MultiFormatLoader·PDF·raw/mime 테스트). 스모크 import 정상.
- eval 회귀(`tests/eval/runner.py`)는 라이브 그래프·벡터스토어·LLM 키가 필요한 라이브러리(현재 `__main__` 진입점·배선 부채 존재)라 이번 작업에서는 미실행. 코퍼스 불변·로더 교체만이므로 검색 품질 영향 없음으로 판단.

## 영향받는 결정

- [ADR-0013](ADR-0013-multi-format-ingestion.md) — 🟣 대체됨. D1~D5 + 다운로드 철회. 파서 격리(D1)의 ABC만 보존.
- [ADR-0016](ADR-0016-identity-risk-sql-gate.md)~[ADR-0018](ADR-0018-decision-audit-log.md) — 본 축소 후 에이전틱 SQL 도구 작업에 착수.
