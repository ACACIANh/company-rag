# 기능 요구사항 (Functional Requirements)

> 현재 구현 상태 기준 (2026-05-23). Phase 1~5 완료.

---

## 상태 범례
| 기호 | 의미 |
|------|------|
| ✅ | 구현 완료 |
| ⚠️ | 부분 구현 / 제한 있음 |
| ❌ | 미구현 |
| 🔲 | Backlog |

---

## 1. 인증 · 인가

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| A-1 | 사용자명/비밀번호로 로그인 → JWT 발급 | ✅ | `POST /auth/token` |
| A-2 | JWT로 본인 정보 조회 | ✅ | `GET /auth/me` |
| A-3 | 만료/위조 토큰 거부 | ✅ | `shared/auth/jwt_handler.py` |
| A-4 | 관리자 전용 엔드포인트 보호 | ✅ | `require_admin` 의존성 |
| A-5 | 사용자별 접근 가능 문서 제한 | ⚠️ | `allowed_doc_ids: []` 이면 전체 허용 (화이트리스트 방식) — **Backlog** |
| A-6 | 비밀번호 해싱 저장 | ❌ | 현재 평문 (`config/users.yaml`) — **Backlog** |
| A-7 | SSO / OAuth 연동 | ❌ | plan.md Phase 5 항목 |

---

## 2. 채팅 (Q&A)

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| B-1 | 자연어 질문 → 답변 반환 | ✅ | `POST /chat` |
| B-2 | 답변에 출처(인용) 포함 | ✅ | `citations` 필드 |
| B-3 | 세션 ID로 멀티턴 대화 유지 | ✅ | `MemorySaver` + `session_id` |
| B-4 | 최근 10턴으로 히스토리 트리밍 | ✅ | `load_memory_node` |
| B-5 | 사용자별 Rate Limiting | ✅ | `/chat` 경로 기준 분당 제한 |
| B-6 | 스트리밍 응답 | ❌ | plan.md에 언급, 미구현 |
| B-7 | 첫 질문창 추천 질문 3개 제안 | 🔲 | Backlog |

---

## 3. RAG 파이프라인

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| C-1 | 질문 자동 재작성 (대명사 해소, 서브 질문 분해) | ✅ | `rewrite_query_node` |
| C-2 | 질문 유형 자동 분류 (doc / tool) | ✅ | `router_node` — LLM 기반 |
| C-3 | 사내 문서 벡터 검색 | ✅ | `retrieve_node` + ChromaDB |
| C-4 | 검색 결과 관련성 채점 (0~1) | ✅ | `grade_documents_node` |
| C-5 | 관련성 부족 시 재검색 (최대 2회) | ✅ | `retry_count` 상한 적용 |
| C-6 | ~~웹 검색 fallback~~ (제거, 역기획서 §9.1) | 🗑️ | `web_search_node` 그래프 경로 제거. `core/` Tavily/DuckDuckGo 어댑터는 에이전틱 `tool_call` 재사용 위해 보존 |
| C-7 | 환각(hallucination) 감지 및 재생성 | ✅ | `check_hallucination_node` |
| C-8 | 사용 권한 기반 문서 필터링 | ✅ | `filter_doc_ids` → ChromaDB `$in` 필터 |
| C-9 | Hybrid Search (Vector + BM25) | ❌ | 현재 Vector Only |
| C-10 | 재순위(Reranker) | ❌ | `shared/reranker/` 폴더 존재, 미연결 |

---

## 4. 도구 호출 (Agent)

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| D-1 | 사내 API 도구 호출 | ⚠️ | `tool_executor_node` — Mock 구현 |
| D-2 | 도구 호출 전 사용자 확인 (HITL) | ✅ | `confirm_node` + `interrupt()` |
| D-3 | 도구별 timeout / 에러 핸들링 | ✅ | 노드 단위 격리 |
| D-4 | 실제 사내 API 연동 | ❌ | Phase 4 이후 예정 |

---

## 5. 문서 인덱싱

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| E-1 | 사내 문서 청킹 → 임베딩 → 저장 | ✅ | `app/ingestion/` 파이프라인 |
| E-2 | 관리자 API로 인덱스 재빌드 | ✅ | `POST /admin/index/rebuild` (비동기) |
| E-3 | 현재 청크 수 조회 | ✅ | `GET /admin/index/status` |
| E-4 | 문서 단위 부분 업데이트 | ❌ | 현재 전체 재빌드만 지원 |

---

## 6. 관리자 기능

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| F-1 | 사용자 목록 조회 | ✅ | `GET /admin/users` |
| F-2 | 사용자별 접근 문서 수정 | ✅ | `PUT /admin/users/{id}/docs` |
| F-3 | 평가셋 실행 | ✅ | `POST /admin/eval/run` |
| F-4 | 평가 결과 이력 조회 | ✅ | `GET /admin/eval/results` (최근 10회) |
| F-5 | 일별 비용 리포트 조회 | ✅ | `GET /admin/cost/report` |
| F-6 | 관리자 UI | ❌ | API만 존재, 프론트 없음 |

---

## 7. 관측성 · 운영

| # | 요구사항 | 상태 | 비고 |
|---|----------|------|------|
| G-1 | LangSmith 트레이싱 | ✅ | `company-rag` 프로젝트 연동 |
| G-2 | LLM 호출 비용 추적 (파일 기록) | ✅ | `shared/observability/` |
| G-3 | 평가셋 회귀 테스트 | ✅ | `tests/eval/runner.py` — recall@5=0.80 |
| G-4 | 부하 테스트 (동시 50명) | ⚠️ | `tests/load/locustfile.py` 존재, 미측정 |
| G-5 | 메트릭 대시보드 (Grafana 등) | ❌ | plan.md 항목, 미구현 |

---

## 8. 비기능 요구사항

| 항목 | 목표 | 현재 상태 |
|------|------|-----------|
| 응답 시간 | 단순 Q&A 5초 이내 | 미측정 |
| 정확도 (recall@5) | 80% 이상 | ✅ 0.80 (Phase 2 기준) |
| 환각률 | 5% 이하 | ✅ check_hallucination 노드 통과율로 측정 가능 |
| 동시 사용자 | 50명 | ⚠️ 미측정 |

---

*출처: `plan/plan.md`, `app/api/`, `app/graph/`, `shared/` 분석 — 2026-05-23*
