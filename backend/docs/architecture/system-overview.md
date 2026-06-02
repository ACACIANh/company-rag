# 시스템 구성도 — 전체 개요 (대분류)

> company-rag 모노레포 전체의 고수준 시스템 구성도.
> 백엔드 내부의 RAG 그래프·권한제어·인제스천 상세는 [backend-internals.md](./backend-internals.md) 참조.

`company-rag`는 LangGraph 기반 사내 문서 RAG 챗봇이다. 프론트엔드(`web/`)와 백엔드(`backend/`)가 형제 관계인 모노레포로 구성되며, 모든 통신은 백엔드 REST/SSE API를 통해서만 이루어진다.

---

## 1. 전체 구성

```mermaid
flowchart LR
    subgraph client["web/ — React SPA (Vite + TS)"]
        UI["채팅 UI / 로그인<br/>SSE 스트리밍 수신"]
    end

    subgraph backend["backend/ — FastAPI"]
        API["app/api<br/>REST + SSE 라우터"]
        GRAPH["app/graph<br/>LangGraph 오케스트레이션"]
        ING["app/ingestion<br/>인덱싱 파이프라인"]
        CORE["core/<br/>ABC 공용 인프라<br/>(LangGraph 불가지)"]
    end

    subgraph data["PostgreSQL"]
        PG[("documents + pgvector<br/>originals · versions<br/>sessions · fga_cache<br/>checkpoints")]
    end

    subgraph ext["외부 서비스"]
        LLM["Anthropic / OpenAI<br/>LLM · Embedding"]
        FGA["OpenFGA<br/>권한 엔진"]
    end

    UI -->|"HTTPS REST + SSE<br/>VITE_API_BASE_URL"| API
    API --> GRAPH
    API --> ING
    GRAPH --> CORE
    ING --> CORE
    CORE --> PG
    CORE --> LLM
    CORE --> FGA
```

- **web/** — 백엔드 코드를 직접 참조하지 않고 `VITE_API_BASE_URL` API로만 통신한다.
- **backend/** — `app/`(API·그래프·인제스천)과 `core/`(공용 인프라)로 나뉜다.
- **PostgreSQL** — 벡터·세션·원본·권한캐시·그래프 체크포인트를 단일 DB에 통합(Redis 미사용).
- **외부 서비스** — LLM/임베딩 provider와 OpenFGA 권한 엔진은 `core/` 인터페이스 뒤에 격리된다.

---

## 2. 레이어 경계 (절대 규칙)

```mermaid
flowchart TB
    subgraph app["app/ — LangGraph를 아는 계층"]
        api2["api/ — FastAPI 라우터·인증·rate limit"]
        graph2["graph/ — StateGraph 노드·엣지"]
        ing2["ingestion/ — Indexer 조립"]
    end

    subgraph core2["core/ — LangGraph 불가지 공용 인프라"]
        abc["ABC 인터페이스 (base.py)<br/>LLMClient · Retriever · Reranker<br/>Embedder · VectorStore · SessionStore ..."]
        impl["pluggable 구현체<br/>(factory로 설정 기반 선택)"]
    end

    store[("저장소 · 외부 API")]

    api2 -->|"ABC만 의존"| abc
    graph2 -->|"ABC만 의존"| abc
    ing2 -->|"ABC만 의존"| abc
    abc --> impl
    impl --> store
```

핵심 불변식 (`backend/CLAUDE.md`):

| 규칙 | 내용 |
|------|------|
| `core/`는 LangGraph를 모른다 | `core/` 어디에도 `langgraph` import 없음. 순수 도메인 로직만. |
| `app/`은 `core/`의 ABC만 의존 | 구현체는 `lifespan`에서 생성 후 `app.state`로 주입. |
| `app/graph/nodes/`는 순수 함수 | State in → State out. side effect는 `core/` 호출로만. |

구현체는 `factory`로 설정(`.env`) 기반 교체된다 — LLM(Anthropic↔OpenAI), Embedder(OpenAI↔SentenceTransformers), 캐시·세션(Postgres↔Memory) 등.

---

## 3. 요청 데이터 흐름 (채팅 1턴)

```mermaid
sequenceDiagram
    participant U as web (SPA)
    participant A as app/api (FastAPI)
    participant G as app/graph (LangGraph)
    participant C as core/ 인프라
    participant P as PostgreSQL
    participant X as LLM / OpenFGA

    U->>A: POST /auth/token (로그인)
    A-->>U: JWT access_token
    U->>A: POST /chat/stream (질문, Bearer JWT)
    A->>G: graph.ainvoke(initial state)
    G->>C: 권한 조회 (FGA)
    C->>X: OpenFGA ListObjects(can_read)
    G->>C: 벡터 검색 (권한 pre-filter)
    C->>P: SELECT ... WHERE path = ANY()
    G->>C: LLM 답변 생성
    C->>X: Anthropic/OpenAI complete
    G-->>A: 토큰 스트림 + 출처
    A-->>U: SSE (token / sources / done)
```

- 인증: `/auth/token`으로 JWT 발급(`config/users.yaml` 기반) → 이후 모든 요청 `Authorization: Bearer`.
- 채팅: `POST /chat/stream`이 LangGraph 그래프를 실행하고 **Server-Sent Events**로 토큰·출처·완료 이벤트를 흘려보낸다.
- 그래프 내부 노드 토폴로지·권한 pre-filter 상세는 [backend-internals.md](./backend-internals.md) 참조.

---

## 4. 컴포넌트 인벤토리

### 4.1 프론트엔드 (`web/src/`)

| 영역 | 구성 | 역할 |
|------|------|------|
| `api/` | `client.ts` | `apiFetch()` HTTP 래퍼 + `streamChat()` SSE 제너레이터. 401→로그아웃, 429→retry-after 처리 |
| `auth/` | `AuthContext`, `LoginPage` | JWT를 localStorage에 보관, `/auth/me`로 프로필 로드 |
| `chat/` | `ChatPage`, `MessageList`, `MessageInput`, `SessionSidebar`, `MarkdownRenderer`, `SourceBadge` | 채팅 UI, 세션 사이드바, 마크다운·출처 렌더링 |

스택: React 18 · TypeScript 5 (strict) · Vite 5 · react-router 6 · TailwindCSS 3 · 상태관리는 Context API, HTTP는 네이티브 `fetch`(별도 라이브러리 없음).

### 4.2 백엔드 API 라우터 (`app/api/`)

| 라우터 | 대표 엔드포인트 | 역할 |
|--------|----------------|------|
| `auth` | `POST /auth/token`, `GET /auth/me` | JWT 발급·현재 사용자 |
| `chat` | `POST /chat`, `POST /chat/stream` | 단발/스트리밍 RAG 답변 |
| `sessions` | `GET /sessions`, `GET /sessions/{id}/messages`, `DELETE /sessions/{id}` | 세션 이력 관리 |
| `documents` | `GET /documents/download` | 원본 파일 다운로드 (FGA 권한 검사) |
| `admin` | `/admin/index/*`, `/admin/eval/*`, `/admin/cost/report`, `/admin/users` | 인덱싱·평가·비용·사용자 (admin role 필수) |

모든 의존성(core 구현체)은 `lifespan`에서 생성되어 `app.state`에 주입되고, `deps.py`가 `get_current_user`·`get_fga_client`·`check_rate_limit` 등으로 핸들러에 공급한다.

### 4.3 core/ 공용 인프라 (19개 모듈)

| 모듈 | 역할 | 매핑 기술 |
|------|------|----------|
| `llm` | LLM 통합 (ABC) | Anthropic / OpenAI |
| `embedder` | 텍스트→벡터 (ABC) | OpenAI / SentenceTransformers |
| `vector_store` | 청크+임베딩 저장·검색 (ABC) | PostgreSQL + pgvector (HNSW) |
| `retriever` | 질문→임베딩→검색 (ABC) | vector_store + embedder |
| `reranker` | 검색결과 재정렬 (ABC) | LLM / RRF / NoOp |
| `chunker` | 문서→청크 (ABC) | 고정크기 슬라이딩 윈도우 |
| `loader` | 파일→문서 (ABC) | Markdown / MultiFormat |
| `parser` | bytea→Markdown (ABC) | PDF / Markdown |
| `indexer` | 인제스천 조율 | loader+chunker+embedder+store |
| `document_original` | 원본(bytea) 보관 (ABC) | PostgreSQL |
| `document_version` | 버전 이력 | PostgreSQL |
| `fga` | OpenFGA 권한+캐시 (ABC) | OpenFGA SDK + PostgreSQL TTL 캐시 |
| `auth` | JWT 발급·검증 | PyJWT (HS256) |
| `session` | 채팅 세션 이력 (ABC) | PostgreSQL / Memory |
| `rate_limiter` | API 속도제한 (ABC) | 슬라이딩 윈도우 (in-memory) |
| `observability` | 추적·비용 측정 | tracer / cost_tracker |
| `orchestrator` | 파이프라인 스텝 실행 | step/pipeline |
| `config` | 환경변수 설정 로딩 | dotenv |
| `models` | 도메인 데이터 클래스 | dataclass |

---

## 5. 데이터 저장소 (PostgreSQL 단일 DB)

```mermaid
erDiagram
    documents {
        text chunk_id PK
        text content
        vector embedding "1536, HNSW"
        text path "권한 pre-filter"
        json metadata
    }
    document_originals {
        text document_id PK
        int version PK
        bytea original_file "불변"
        text folder_path
        text content_hash "SHA-256"
    }
    document_versions {
        text document_id PK
        int version PK
        text content_hash
        timestamptz deleted_at "soft-delete"
    }
    chat_sessions {
        text thread_id PK
        text user_id
        text title
    }
    chat_messages {
        bigserial id PK
        text thread_id FK
        text role
        json sources
    }
    fga_permission_cache {
        text user_id PK
        json folders
        timestamptz expires_at "TTL 60s"
    }
    chat_sessions ||--o{ chat_messages : contains
```

| 테이블 | 용도 | 담당 모듈 |
|--------|------|----------|
| `documents` | 청크 + 임베딩 (벡터 검색) | `vector_store.postgres_store` |
| `document_originals` | 원본 파일(bytea), 다운로드·증빙 | `document_original.postgres_store` |
| `document_versions` | 문서 버전 이력(soft-delete) | `document_version.postgres_store` |
| `chat_sessions` / `chat_messages` | 세션 메타·메시지 | `session.adapters.postgres` |
| `fga_permission_cache` | 사용자별 읽기 가능 폴더 캐시 | `fga.cache.postgres` |
| `langgraph_checkpoints` | 그래프 상태(HITL 복구) | langgraph(`AsyncPostgresSaver`) |

> 설계 결정: FGA 캐시는 Redis 대신 PostgreSQL TTL 캐시 사용(기존 DB 재사용, TTL 60초로 충분). 근거 ADR-0009.

---

## 6. 기술 스택 요약

| 구분 | 기술 |
|------|------|
| 프론트 | React 18, TypeScript 5, Vite 5, react-router 6, TailwindCSS 3, Vitest |
| 백엔드 | Python 3.11+, FastAPI, LangGraph, langchain-anthropic |
| LLM / 임베딩 | Anthropic Claude / OpenAI (설정으로 교체) |
| 벡터 검색 | PostgreSQL + pgvector (HNSW) |
| 권한 | OpenFGA (department/folder 트리) + PostgreSQL TTL 캐시 |
| 인증 | JWT (PyJWT, HS256) |
| 통신 | REST + Server-Sent Events (스트리밍) |

---

## 부록 — 참조

- 백엔드 내부 상세 구성도: [backend-internals.md](./backend-internals.md)
- 권한 RAG 설계: `backend/DESIGN.md`
- 결정 기록: `backend/docs/superpowers/decisions/` (ADR-0009 FGA 캐시, ADR-0013 다중 포맷 인제스천 등)
