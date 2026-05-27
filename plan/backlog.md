# Backlog

카테고리 태그: `#perf` `#dx` `#feat` `#refactor` `#test` `#infra` `#doc` `#bug`

---

## High

- `#perf` Hybrid Search (C-9) — 현재 Vector Only, BM25 결합으로 recall 향상 / 별도 BM25 인덱스 검토

### 🔍 Query Rewriting (멀티턴 검색 품질 개선) — ref: SKT Enterprise 블로그

- `#perf` `#feat` **Router Node에 재작성 판단 로직 추가** — `router_node`에서 쿼리 재작성 필요 여부(`none` / `contextual` / `multi_query`) 동시 판단; `AgentState`에 `rewritten_query`, `rewrite_strategy` 필드 추가
- `#feat` **Contextual Query Rewriter 노드 신설** — `app/graph/nodes/query_rewriter.py`; 멀티턴 히스토리 + 현재 질문 → 완전한 단독 쿼리로 변환; **경량 LLM(Haiku) 사용**; retry + timeout 필수
- `#perf` **Multi-Query + RRF 검색** — 복합 질문을 하위 쿼리 2~3개로 분해 후 병렬 검색, Reciprocal Rank Fusion으로 결과 병합; threshold ↑ + top-k ↓ 로 속도 보상

<!-- 빠르게 처리해야 하는 개선사항 -->

## Medium

- `#perf` `#infra` 임베딩 차원 1536 업그레이드 — 현재 차원에서 text-embedding-3-small 1536차원으로 변경; 기존 문서 재임베딩 필요
- `#feat` 제공 기능 안내 라우터 노드 추가 — "뭘 할 수 있어?", "기능이 뭐야?" 등 기능 문의를 감지해 `feature_info` 경로로 분기하는 `router_node` 케이스 추가; 현재 `어시스턴트 기능 안내 응답` 항목의 라우팅 레이어 구현
- `#infra` 배포를 위한 컨테이너화 — Dockerfile(app/worker 분리) + docker-compose(app, postgres, redis) 작성, `.env` 주입 방식 정의. _현재 개발 단계에서는 venv로 충분; FastAPI 외부 배포 또는 벡터 DB 로컬 구동 시점에 착수_
- `#feat` 스트리밍 응답 (B-6) — `POST /chat` SSE 또는 WebSocket 스트리밍, 프론트 연동 포함
- `#feat` 대화 세션 목록 사이드바 — 좌측 세션 리스트(신규/이전 대화 전환), `GET /sessions` 엔드포인트 + 세션 제목 자동 생성(첫 질문 앞 20자), 세션 히스토리 DB 영속화(로그아웃 후 재로그인 시 복원), 프론트 상태 관리 포함
- `#feat` 열람 가능 문서 목록 표시 — `GET /docs` 엔드포인트(JWT 기반 필터링) + 프론트 사이드바/첫 화면 칩 표시
- `#feat` 첫 질문창 진입 시 추천 질문 3개 제안 (빈 채팅 화면에 샘플 질문 버튼 표시)
- `#feat` **어시스턴트 기능 안내 응답** — 사용자가 "뭘 할 수 있어?", "기능이 뭐야?" 등 기능 문의 시 할 수 있는 작업 목록(문서 검색, 웹 검색, Q&A 등)을 안내하는 응답 추가
- `#feat` **OpenFGA 권한 확인 응답** — OpenFGA 연동 후, 사용자가 접근 불가 문서를 조회하거나 권한 오류 발생 시 "해당 문서에 접근 권한이 없습니다" 형태의 명확한 안내 메시지 추가

<!-- 다음 Phase 계획 시 고려할 항목 -->

- `#perf` **Router용 LLM 경량화 분리** — Router/Rewriter 전용으로 `claude-haiku-4-5` 사용, 메인 응답 LLM과 분리; 비용·속도 개선
- `#perf` **HyDE (Hypothetical Document Embeddings) 실험** — 질문 → 가상 답변 생성 → 답변으로 Vector 검색; `tests/eval/runner.py`로 on/off 회귀 비교 필수; 사내 문서 도메인에서만 적용 검토
- `#feat` **Step-Back Prompting** — 복잡한 질문에서 상위 개념 질문 먼저 생성 후 검색; 사규·법률 등 계층적 문서 구조에 유효; 구현 복잡도 높음

<!-- 언젠가 하면 좋을 것들 -->

---

> 작업 시작 시 GitHub Issue로 옮기고 여기서 삭제.
