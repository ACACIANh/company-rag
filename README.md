# company-rag

LangGraph 기반 RAG 챗봇 학습 프로젝트.

회사 내부 문서(`docs/`)를 대상으로 RAG Q&A를 구현합니다. 라우팅(문서검색/도구호출/기능안내), Self-RAG(문서 평가 + 환각 검사 후 재시도), 멀티턴 메모리, HITL(민감 도구 승인), FGA 기반 접근 제어를 포함합니다.

> **현재 단계**: Phase 1~5 완료. `backend/core/` 공용 인프라 + `backend/app/` LangGraph 워크플로우(FastAPI API) + 웹 프론트(`web/`)가 동작합니다.

---

## 프로젝트 구조

```
company-rag/
├── backend/                  # 백엔드 루트 (실행·테스트 작업 디렉터리)
│   ├── app/                  # LangGraph 워크플로우 + FastAPI API
│   │   ├── api/              # FastAPI 엔트리(chat/auth/sessions/admin) + deps
│   │   ├── graph/            # builder, state(AgentState), edges, prompts
│   │   │   ├── nodes/        # 순수 함수 노드 (router, retrieve, grade 등)
│   │   │   └── tools/        # 에이전트 도구 (registry + permission/sql/audit 핸들러)
│   │   └── ingestion/        # 문서 → 청크 → 임베딩 → 벡터 저장소 인덱싱
│   ├── core/                 # 공용 RAG 인프라 (LangGraph 무관, ABC + Factory)
│   │   ├── loader/           # MarkdownLoader
│   │   ├── parser/           # 파서 ABC + MarkdownParser (ADR-0019 보존)
│   │   ├── chunker/          # FixedSizeChunker
│   │   ├── embedder/         # OpenAIEmbedder / SentenceTransformerEmbedder
│   │   ├── vector_store/     # PostgreSQL(pgvector) (ABC + Factory)
│   │   ├── retriever/        # BasicRetriever + 웹검색 어댑터(Tavily/DuckDuckGo)
│   │   ├── reranker/         # NoOp / RRF / LLM Reranker (ABC + Factory)
│   │   ├── llm/              # LLMClient ABC + OpenAI/Anthropic + LangChain 어댑터
│   │   ├── session/          # 세션 저장소 (memory/postgres)
│   │   ├── auth/             # JWT 핸들러 + 인증 ABC
│   │   ├── fga/              # OpenFGA 클라이언트 + 권한 검증(permission_validator) + PostgreSQL TTL 캐시
│   │   ├── sql/              # SQL 카탈로그/게이트/위험도/테이블 스키마 (SQL 도구용)
│   │   ├── rate_limiter/     # 인메모리 레이트 리미터
│   │   ├── indexer/          # 문서 → 청크 → 벡터 저장소
│   │   ├── orchestrator/     # 공통 오케스트레이션 유틸 (학습용)
│   │   ├── observability/    # cost_tracker, tracer, cache, sinks, eval, audit (학습용)
│   │   ├── models.py         # Chunk, SearchResult, Answer 등 DTO
│   │   └── config.py         # 환경변수 로드
│   ├── scripts/              # build_index, seed_fga, 평가/마이그레이션 스크립트
│   ├── config/               # 설정 파일
│   ├── fga/                  # OpenFGA 모델/시드
│   ├── tests/                # 단위 테스트 (core/ + app/) + eval/ + load/
│   │   └── eval/             # questions.yaml + runner.py (회귀 채점)
│   ├── docs/                 # 회사 내부 문서 (Q&A 대상) + 가이드
│   │   ├── langgraph-guide/  # LangGraph 학습 노트 (INDEX.md 진입점)
│   │   └── superpowers/      # ADR(decisions) · plans · specs
│   ├── plan/                 # 작업 계획
│   ├── reference/            # 참고 자료
│   ├── docker-compose.yml    # PostgreSQL(pgvector) + OpenFGA
│   └── CLAUDE.md             # 작업 규칙 및 아키텍처 결정 (ADR)
└── web/                      # Vite + React + TypeScript 프론트엔드
```

---

## 빠른 시작

백엔드 명령은 모두 `backend/`를 작업 디렉터리로 실행합니다.

```bash
cd backend

# 1. 가상환경 + 의존성
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip3 install -e ".[dev]"            # 런타임+개발 의존성 (pyproject.toml)

# 2. 인프라 기동 (PostgreSQL + OpenFGA)
docker compose up -d
./scripts/fga_init.sh               # FGA_STORE_ID 획득 후 .env에 입력

# 3. 환경변수
cp .env.example .env
# .env에 OPENAI_API_KEY (또는 ANTHROPIC_API_KEY), JWT_SECRET, FGA_STORE_ID 입력

# 4. 문서 인덱싱 (최초 1회)
python3 -m scripts.build_index

# 5. API 서버 기동
uvicorn app.api.chat:app --reload
```

### `.env` 최소 설정

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
JWT_SECRET=                          # 필수. 미설정 시 서버 기동 거부 (생성: python -c "import secrets; print(secrets.token_urlsafe(48))")
POSTGRES_DSN=postgresql://fga:fga@localhost:5432/app
FGA_API_URL=http://localhost:8080
FGA_STORE_ID=
```

전체 항목은 `.env.example` 참고.

---

## 아키텍처

### `app/graph` — LangGraph 워크플로우

상태는 `AgentState(TypedDict)` 단일 스키마를 사용합니다(`MessagesState`·임의 dict 금지).

흐름:

```
START → load_memory → rewrite_query → router  (route 필드로 4분기)

  ├─ doc_search → [multi_query] → permission → retrieve → grade_documents
  │      ├─(품질 미달)→ increment_retry → rewrite_query  (재시도, 임계값 제한)
  │      └─(통과)→ generate → check_hallucination → save_memory → END
  │                              └─(환각)→ generate  (재생성)
  │
  ├─ agent → tool_gate → confirm(interrupt) → justify_execute → agent  (도구 루프)
  │      └─(도구 없음·직접답변)→ agent_answer → save_memory → END
  │
  ├─ capability → save_memory → END
  │
  └─ clarify(interrupt) → permission(doc_search) 또는 agent 로 재분기
```

- **라우터**: `router_node`가 `route` 필드로 doc_search/agent/capability 분기 (신뢰도 0.75 미만이면 `clarify`로 HITL 재질문)
- **Self-RAG**: `grade_documents` + `check_hallucination` 평가 후 `increment_retry`로 재시도(임계값 제한)
- **HITL**: `interrupt()` 2곳 — (1) agent 도구 호출 시 사유 기재(`confirm`), (2) 라우터 모호 분기(`clarify`). checkpointer 필수
- **FGA**: 폴더 트리 pre-filter — `ListObjects(can_read, folder)`로 읽을 수 있는 폴더 목록을 받아 청크 `path`가 그 목록에 정확 매칭(`path = ANY`)되는 것만 검색 전 통과

### `core/` — 워크플로우 무관 공용 인프라

ABC + Factory 패턴으로 LLM 프로바이더(OpenAI/Anthropic), 벡터 저장소(PostgreSQL), 리랭커, 세션 저장소를 추상화합니다(임베더는 `core/`에 ABC만 두고, 구현체 선택은 app 계층 `app/ingestion/embedder.py`의 `get_embedder()`가 담당). LangChain 통합용 얇은 어댑터(`core/*/adapters/`)도 포함합니다.

> 일부 모듈(`orchestrator/`, `observability/eval/`, 일부 어댑터)은 학습 목적 + 구현체 교체 가능성을 위해 유지되는, 현재 워크플로우에 미연결된 추상화입니다.

### 아키텍처 결정 (요약)

| 영역 | 결정 |
|---|---|
| 상태 관리 | `AgentState(TypedDict)` 단일 스키마 |
| checkpointer | 운영: `AsyncPostgresSaver` / 기본값: `MemorySaver` |
| 라우팅 | `router_node`의 `route` 필드 분기 |
| 멀티쿼리 | 쿼리 분해 + 병렬 검색 + RRF merge |
| 스트리밍 | SSE (`/chat` 스트리밍) |
| HITL/가드레일 | 결정론적 가드레일 우선, 민감 도구는 `interrupt()` |
| 접근 제어 | OpenFGA(ReBAC: 부서·폴더 트리 관계 그래프) + PostgreSQL `path` 정확매칭 pre-filter |

상세 근거는 `CLAUDE.md`와 `docs/superpowers/decisions/`(ADR)를 참고하세요.

---

## 테스트

`backend/`를 작업 디렉터리로 실행합니다.

```bash
cd backend
pytest tests/ -q          # 전체
pytest tests/core/        # core 단위 테스트
pytest tests/app/         # app(그래프/API) 테스트
```

---

## 평가

`tests/eval/runner.py`의 `run_eval(run, ...)`에 워크플로우의 `run(question) -> Answer` 함수를 주입하면 `tests/eval/questions.yaml`을 대상으로 회귀 점수(recall@k / keyword_hit_rate 등)를 채점합니다. 변경 후 회귀 확인은 DoD 항목입니다.

```bash
python3 -m scripts.eval_rag_basic     # 그래프를 주입해 회귀 채점
```

---

## 기술 스택

- **LLM**: OpenAI GPT / Anthropic Claude (`LLMClient` ABC + Factory)
- **임베딩**: OpenAI `text-embedding-3-small` (1536차원) / SentenceTransformer 대체 가능
- **벡터 저장소**: PostgreSQL (pgvector)
- **접근 제어**: OpenFGA (ReBAC) + PostgreSQL TTL 캐시
- **SQL 도구**: PostgreSQL 직접 질의 에이전트 (`sqlglot` AST로 참조 테이블 추출·위험도 분류, 읽기/쓰기 이중 계정 + WHERE 필수 가드)
- **오케스트레이션**: LangGraph (+ LangChain 어댑터)
- **세션/체크포인트**: LangGraph 체크포인터 (`langgraph-checkpoint-postgres`) — 운영은 `AsyncPostgresSaver`로 HITL interrupt/resume 영속화, 미주입 시 `MemorySaver`(인메모리) 폴백
- **API**: FastAPI (SSE 스트리밍)
- **테스트**: pytest, pytest-mock

---

## 참조

- `CLAUDE.md` — 작업 규칙, 아키텍처 결정
- `docs/langgraph-guide/INDEX.md` — LangGraph 학습 노트 진입점
- `docs/superpowers/decisions/` — ADR 목록
- 원본 위키독스: https://wikidocs.net/book/16723
