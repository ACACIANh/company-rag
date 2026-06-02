# ADR 인덱스

> 자동 생성 파일 — 직접 편집 금지.
> 갱신: `cd backend && .venv/bin/python -m scripts.gen_adr_index`

| ADR | 제목 | 상태 |
|-----|------|------|
| [0001](ADR-0001-decision-log-mechanism.md) | 결정 기록 메커니즘 도입 | 🟢 적용완료 |
| [0002](ADR-0002-fga-cache-strategy.md) | listObjects 캐싱 전략 | 🟢 적용완료 |
| [0003](ADR-0003-frontend-architecture.md) | 프론트엔드 추가 방향성 | 🟢 적용완료 |
| [0004](ADR-0004-legacy-doc-owner-policy.md) | 구문서 소유자 미지정 시 일괄 처리 방침 | 🟣 대체됨 |
| [0005](ADR-0005-llm-selection.md) | RAG LLM 선택 | 🟢 적용완료 |
| [0006](ADR-0006-openfga-hosting.md) | OpenFGA 호스팅 방식 | 🟢 적용완료 |
| [0007](ADR-0007-reranker-eval-metrics.md) | Reranker 임팩트 측정 지표 설계 | 🟢 적용완료 |
| [0008](ADR-0008-reranker-implementation.md) | Reranker 구현체 선택 | 🟢 적용완료 |
| [0009](ADR-0009-fga-cache-postgresql.md) | listObjects 캐싱 전략 — Redis → PostgreSQL 변경 | 🟢 적용완료 |
| [0010](ADR-0010-karpathy-guidelines-audit.md) | Karpathy Guidelines 적용 감사 보고서 | 🟢 적용완료 |
| [0011](ADR-0011-folder-tree-access-model.md) | 접근 권한 모델 — 문서/팀/민감도 → 폴더 트리 pre-filter 전환 | 🟣 대체됨 |
| [0012](ADR-0012-document-index-sync.md) | 문서 인덱스 동기화 — 버전 스냅샷 + 최신 프로젝션 | 🟢 적용완료 |
| [0013](ADR-0013-multi-format-ingestion.md) | 다중 포맷 문서 인제스천 — 파서 격리 + 통일 중간표현(Markdown) | 🟣 대체됨 |
| [0014](ADR-0014-manual-test-seed-rebuild.md) | 수동 테스트용 시드 데이터 전면 재구성 | 🟢 적용완료 |
| [0015](ADR-0015-fga-public-private-super-reader.md) | FGA 권한 모델 확장 — public/private/dept/super_reader 4축 모델 | 🟢 적용완료 |
| [0016](ADR-0016-identity-risk-sql-gate.md) | 신원 × 위험도 교차 게이트로 자율 SQL 도구를 통제한다 | 🟢 적용완료 |
| [0017](ADR-0017-sql-risk-classification.md) | SQL 위험도 분류 — AST 확정 + LLM 보강 | 🟢 적용완료 |
| [0018](ADR-0018-decision-audit-log.md) | 게이트 결정·SQL 실행 감사 로그 인프라 | 🟢 적용완료 |
| [0019](ADR-0019-scope-down-ingestion.md) | 기획 축소 — 다중 포맷·원본 보관·다운로드 철회, Markdown 단일 인제스천 복귀 | 🟢 적용완료 |
| [0020](ADR-0020-sql-gate-prerequisite-infra.md) | 신원×위험도 SQL 게이트의 전제 인프라 | 🟢 적용완료 |
| [0021](ADR-0021-sql-schema-value-hints.md) | NL→SQL 생성 — 카테고리형 컬럼 값 힌트(value hints) | ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0022](ADR-0022-router-route-discrimination.md) | 라우터 doc_search↔tool_call 분류 정확도 개선 | ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0027](ADR-0027-justify-and-approve-self-service-gate.md) | DBA 부재 가정 — `NEEDS_APPROVAL`을 `JUSTIFY_AND_APPROVE`(사유 기재 자가승인)로 개정 | 🔵 승인됨 |

## 상태 범례

🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기
