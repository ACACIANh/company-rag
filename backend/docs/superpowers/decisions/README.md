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
| [0012](ADR-0012-document-index-sync.md) | 문서 인덱스 동기화 — 버전 스냅샷 + 최신 프로젝션 | 🟢 적용완료 (부분 축소) |
| [0013](ADR-0013-multi-format-ingestion.md) | 다중 포맷 문서 인제스천 — 파서 격리 + 통일 중간표현(Markdown) | 🟣 대체됨 |
| [0014](ADR-0014-manual-test-seed-rebuild.md) | 수동 테스트용 시드 데이터 전면 재구성 | 🟢 적용완료 |
| [0015](ADR-0015-fga-public-private-super-reader.md) | FGA 권한 모델 확장 — public/private/dept/super_reader 4축 모델 | 🟢 적용완료 |
| [0016](ADR-0016-identity-risk-sql-gate.md) | 신원 × 위험도 교차 게이트로 자율 SQL 도구를 통제한다 | 🟣 대체됨 |
| [0017](ADR-0017-sql-risk-classification.md) | SQL 위험도 분류 — AST 확정 + LLM 보강 | 🟢 적용완료 |
| [0018](ADR-0018-decision-audit-log.md) | 게이트 결정·SQL 실행 감사 로그 인프라 | 🟢 적용완료 |
| [0019](ADR-0019-scope-down-ingestion.md) | 기획 축소 — 다중 포맷·원본 보관·다운로드 철회, Markdown 단일 인제스천 복귀 | 🟢 적용완료 |
| [0020](ADR-0020-sql-gate-prerequisite-infra.md) | 신원×위험도 SQL 게이트의 전제 인프라 | 🟢 적용완료 |
| [0021](ADR-0021-sql-schema-value-hints.md) | NL→SQL 생성 — 카테고리형 컬럼 값 힌트(value hints) | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0022](ADR-0022-router-route-discrimination.md) | 라우터 doc_search↔tool_call 분류 정확도 개선 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0023](ADR-0023-tool-call-agentic-loop.md) | tool_call 경로를 게이트된 도구-디스패치 ReAct 루프로 전환 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0024](ADR-0024-hitl-api-resume.md) | HITL 종단 완결 — 계획된 동작 노출 + API resume 루프 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0027](ADR-0027-justify-and-approve-self-service-gate.md) | DBA 부재 가정 — `NEEDS_APPROVAL`을 `JUSTIFY_AND_APPROVE`(사유 기재 자가승인)로 개정 | 🟢 적용완료 |
| [0028](ADR-0028-capability-permission-model.md) | SQL 게이트를 OpenFGA capability 모델로 통일 (SP2a) | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0029](ADR-0029-permission-management-tool.md) | 권한 관리 도구 manage_permission (SP2b) | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0030](ADR-0030-web-interrupt-rendering.md) | web interrupt(HITL JUSTIFY) 대화형 렌더링 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0031](ADR-0031-router-agent-label-permission-routing.md) | 라우터 route 라벨 `agent` 명명 + 권한관리 라우팅 포함 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0032](ADR-0032-gated-tool-single-arg.md) | 게이트 도구 단일 입력 인자(`__arg1`) 처리 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0033](ADR-0033-terminology-naming-deadcode-cleanup.md) | 캡슐화 기반 명명 표준 + 유령 SQL 코드 제거 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0034](ADR-0034-business-write-gate.md) | 게이트 통제 하 business 스키마 쓰기 허용(UPDATE/DELETE) | 🟢 적용완료 |
| [0035](ADR-0035-capability-discovery-route.md) | 기능 안내 route 추가 — capability discovery | 🟢 적용완료 |
| [0036](ADR-0036-no-source-notice-scope.md) | "출처를 찾지 못했습니다" 멘트 — RAG 경로 한정 표시 | 🟢 적용완료 |
| [0037](ADR-0037-citation-relevance-filter.md) | citations — 실제 사용 문서만 표시 | 🟢 적용완료 |
| [0038](ADR-0038-followup-parroting-bug.md) | 재질문 앵무새 버그 — chat_history가 생성 답변을 지배하는 문제 | 🟢 적용완료 |
| [0039](ADR-0039-new-session-input-autofocus.md) | "+ 새 대화" 클릭 시 입력창 자동 포커싱 | 🟢 적용완료 |
| [0040](ADR-0040-audit-history-tool.md) | query_audit_history 도구 — ReAct 루프 내 감사 이력 조회 | 🟢 적용완료 |
| [0041](ADR-0041-permission-agent-rename-query.md) | ToolHandler → ToolAgent 개명 + PermissionAgent query 액션 | 🟢 적용완료 |
| [0042](ADR-0042-router-clarify-interrupt.md) | 라우터 모호 질문 clarify — HITL 범위 확장 | 🟢 적용완료 |
| [0043](ADR-0043-capability-matrix-justify-only.md) | capability 매트릭스 정리 — SELECT만 즉시허용, 그 외 위험군은 justify-only | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0044](ADR-0044-seed-fga-prune-reconcile.md) | seed_fga --prune — 추가식 시드의 잔재 정리(재조정) | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |
| [0045](ADR-0045-permission-query-capabilities.md) | 권한 조회 스냅샷에 capability 권한 노출 | 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 --> |

## 상태 범례

🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기
