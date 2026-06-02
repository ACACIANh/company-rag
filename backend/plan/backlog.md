# Backlog

카테고리 태그: `#perf` `#dx` `#feat` `#refactor` `#test` `#infra` `#doc` `#bug`

---

## High

- `#bug` **환각 검사 오탐 → 무력한 재생성 루프** — 문서 기반의 멀쩡한 답변을 `check_hallucination_node`가 반복적으로 `hallucination_passed=False`로 판정. **LangSmith 트레이스로 확인**(project `company-rag`): "배포는 어떤 절차로 진행해?"에서 `generate`가 retry_count 상한(3)까지 4회 실행, 매번 환각 검사 실패, 각 `generate` output은 정상적인 배포 절차 답변. **원인**: 여러 문서(deployment-guide·incident-response·engineering-standards 등)를 종합·의역한 답변은 어느 문서에도 글자 그대로 없어, "문서에 없는 내용이면 NO"라는 엄격한 이진 검사가 false positive를 냄. 게다가 재생성 시 *"더 보수적으로"* 같은 피드백이 프롬프트에 없어 비슷한 답변이 반복 생성 → 루프가 교정 기능을 못 함. (부차: `passed = "YES" in response`라 LLM이 장문/한국어로 답하면 파싱 실패로 NO 처리될 여지 — 단 LLM raw 응답은 아래 `#dx` 갭으로 트레이스 미계측이라 미확정.) **수정 후보**: (a) 종합·요약을 허용하도록 환각 프롬프트 완화 또는 청크 단위 근거 매칭, (b) 재생성 시 직전 실패 사유를 프롬프트에 피드백, (c) 환각 임계/판정을 점수화. 관련: `app/graph/nodes/check_hallucination.py`, `app/graph/prompts.py`(`CHECK_HALLUCINATION`), `edges.py`(`route_after_hallucination`).
- `#bug` **스트리밍 답변 중복 출력 (재생성 ↔ 토큰 큐)** — 위 재생성 루프와 결합된 UX 버그. 프론트(`/chat/stream`)에서 동일 답변이 재시도 횟수만큼(~3-4회) 반복 표시됨. 비스트리밍 `POST /chat`은 마지막 `answer`만 반환해 정상이라 curl에서는 안 잡힘. **원인**: `generate_node`가 매 재생성마다 같은 `token_queue`에 토큰을 다시 흘리는데 이전 답변을 무효화하는 신호가 없어 프론트가 누적. **수정 후보**: (a) 재생성 직전 큐에 `reset`/`regenerate` 이벤트 방출 → 프론트 버퍼 클리어, (b) 중간 재생성은 큐에 흘리지 않고 최종본만 스트림. 관련: `app/graph/nodes/generate.py`, `app/graph/builder.py`, `web/src/api/client.ts`(`streamChat`). (근본 원인은 위 환각 오탐 — 그쪽이 해결되면 빈도 급감)
- `#dx` **LLM 호출 LangSmith 미계측** — `LANGCHAIN_TRACING_V2=true`로 LangGraph 노드 state는 트레이스에 잡히나, `core/llm`이 OpenAI SDK를 직접 호출(`chat.completions.create`)하고 `ChatOpenAI`/`wrap_openai`를 안 써서 **LLM run(프롬프트·raw 응답·토큰/비용)이 트레이스에 없음**. 환각 검사 LLM이 실제로 뭐라 답했는지 등 디버깅 정보가 가려짐. **수정 후보**: `langsmith.wrappers.wrap_openai`로 SDK 클라이언트 래핑 또는 노드에 `@traceable`. 관련: `core/llm/openai_client.py`, `core/llm/anthropic_client.py`.
- `#perf` Hybrid Search (C-9) — 현재 Vector Only, BM25 결합으로 recall 향상 / 별도 BM25 인덱스 검토

<!-- 빠르게 처리해야 하는 개선사항 -->

## Medium

- `#perf` `#infra` 임베딩 차원 1536 업그레이드 — 현재 차원에서 text-embedding-3-small 1536차원으로 변경; 기존 문서 재임베딩 필요
- `#feat` 제공 기능 안내 라우터 노드 추가 — "뭘 할 수 있어?", "기능이 뭐야?" 등 기능 문의를 감지해 `feature_info` 경로로 분기하는 `router_node` 케이스 추가; 현재 `어시스턴트 기능 안내 응답` 항목의 라우팅 레이어 구현
- `#infra` 배포를 위한 컨테이너화 — Dockerfile(app/worker 분리) + docker-compose(app, postgres, redis) 작성, `.env` 주입 방식 정의. _현재 개발 단계에서는 venv로 충분; FastAPI 외부 배포 또는 벡터 DB 로컬 구동 시점에 착수_
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
