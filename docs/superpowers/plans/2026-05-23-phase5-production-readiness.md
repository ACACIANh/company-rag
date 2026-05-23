# Phase 5: 운영 준비 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JWT 인증, 문서 ACL 필터링, Rate Limiting, 비용 모니터링, 어드민 API, Locust 부하 테스트를 추가해 프로덕션 배포 준비를 완료한다.

**Architecture:** 보안 우선(Option A) — 인증 레이어를 먼저 구축하고, ACL 필터를 검색 레이어에 주입한 후, 운영 도구(Rate Limiting / 비용 모니터링 / 어드민 API)를 순서대로 쌓는다. 각 태스크는 이전 태스크의 인터페이스에만 의존하므로 독립적으로 테스트 가능하다.

**Tech Stack:** FastAPI, PyJWT, LangGraph, ChromaDB, Locust

---

## 파일 구조

### 신규 생성
```
config/users.yaml                              # Mock 사용자 테이블
shared/auth/__init__.py
shared/auth/base.py                            # AuthUser TypedDict
shared/auth/jwt_handler.py                     # JWT encode/decode
shared/rate_limiter/__init__.py
shared/rate_limiter/base.py                    # RateLimiter ABC
shared/rate_limiter/in_memory.py               # 슬라이딩 윈도우 구현
shared/observability/sinks/__init__.py
shared/observability/sinks/base.py             # CostSink ABC
shared/observability/sinks/file_sink.py        # JSONL 파일 출력
shared/observability/cost_tracker.py           # fan-out + 가격 계산
app/api/auth.py                                # POST /auth/token, GET /auth/me
app/api/deps.py                                # get_current_user, require_admin, check_rate_limit
app/api/admin.py                               # /admin/* 엔드포인트
tests/shared/auth/test_jwt_handler.py
tests/shared/rate_limiter/test_in_memory.py
tests/shared/observability/test_cost_tracker.py
tests/app/api/test_auth.py
tests/app/api/test_admin.py
tests/load/locustfile.py
```

### 수정
```
requirements.txt                               # PyJWT, locust 추가
shared/config.py                               # JWT_SECRET, RATE_LIMIT_PER_MINUTE 추가
shared/vector_store/base.py                    # search() filter_doc_ids 파라미터 추가
shared/vector_store/chroma_store.py            # where 필터 적용
shared/retriever/base.py                       # retrieve() filter_doc_ids 파라미터 추가
shared/retriever/basic_retriever.py            # filter_doc_ids 전달
app/graph/state.py                             # user_id, allowed_doc_ids 필드 추가
app/graph/nodes/retrieve.py                    # allowed_doc_ids 읽어 retriever에 전달
app/graph/nodes/generate.py                    # cost_tracker.track() 추가
app/graph/builder.py                           # answer_question() user_id/allowed_doc_ids 추가
app/api/chat.py                                # Depends(get_current_user) + State 주입
tests/app/graph/nodes/test_retrieve.py         # filter_doc_ids 인수 추가
```

---

## Task 0: 브랜치 생성 + 의존성 추가

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 브랜치 생성**

```bash
git checkout -b feat/phase-5
```

- [ ] **Step 2: 의존성 추가**

`requirements.txt` 끝에 두 줄 추가:

```
PyJWT>=2.8.0
locust>=2.29.0
```

- [ ] **Step 3: 설치 확인**

```bash
pip install PyJWT locust
python -c "import jwt; import locust; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add requirements.txt
git commit -m "chore: add PyJWT and locust dependencies"
```

---

## Task 1: Mock 사용자 테이블 + Config JWT 설정

**Files:**
- Create: `config/users.yaml`
- Modify: `shared/config.py`

- [ ] **Step 1: config/ 디렉터리 + users.yaml 생성**

`config/users.yaml`:
```yaml
users:
  - username: admin
    password: admin123
    user_id: user-admin
    roles:
      - admin
      - user
    allowed_doc_ids: []
  - username: alice
    password: alice123
    user_id: user-alice
    roles:
      - user
    allowed_doc_ids: []
  - username: restricted
    password: restricted123
    user_id: user-restricted
    roles:
      - user
    allowed_doc_ids:
      - docs/company/hr_policy.md
```

> `allowed_doc_ids: []` = 전체 문서 허용. 비어 있지 않으면 해당 문서만 허용.

- [ ] **Step 2: shared/config.py에 JWT + Rate Limit 설정 추가**

기존 `Config` dataclass에 세 필드 추가:

```python
@dataclass
class Config:
    llm_provider: str
    llm_model: str
    openai_api_key: str
    anthropic_api_key: str
    vector_store: str
    chroma_mode: str
    chroma_path: str
    embedding_model: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    jwt_secret: str          # 추가
    jwt_expire_minutes: int  # 추가
    rate_limit_per_minute: int  # 추가
```

`load_config()` 함수에 세 줄 추가:

```python
def load_config() -> Config:
    return Config(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        vector_store=os.getenv("VECTOR_STORE", "chroma"),
        chroma_mode=os.getenv("CHROMA_MODE", "embedded"),
        chroma_path=os.getenv("CHROMA_PATH", "./.chroma"),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        ),
        qdrant_url=os.getenv("QDRANT_URL", ""),
        qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "documents"),
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-prod"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
    )
```

- [ ] **Step 3: 커밋**

```bash
git add config/users.yaml shared/config.py
git commit -m "feat(config): add JWT secret, rate limit, mock user table"
```

---

## Task 2: AuthUser TypedDict + JWT 핸들러

**Files:**
- Create: `shared/auth/__init__.py`
- Create: `shared/auth/base.py`
- Create: `shared/auth/jwt_handler.py`
- Test: `tests/shared/auth/test_jwt_handler.py`

- [ ] **Step 1: 테스트 작성**

`tests/shared/auth/test_jwt_handler.py`:
```python
import pytest
from shared.auth.jwt_handler import create_token, decode_token


def test_create_and_decode_token():
    token = create_token(
        user_id="user-alice",
        roles=["user"],
        allowed_doc_ids=["docs/company/policy.md"],
        secret="test-secret",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == "user-alice"
    assert payload["roles"] == ["user"]
    assert payload["allowed_doc_ids"] == ["docs/company/policy.md"]


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not.a.valid.token", secret="test-secret")


def test_decode_wrong_secret_raises():
    token = create_token("u1", ["user"], [], secret="secret-a", expire_minutes=60)
    with pytest.raises(Exception):
        decode_token(token, secret="secret-b")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/shared/auth/test_jwt_handler.py -v
```
Expected: `ModuleNotFoundError` (아직 구현 없음)

- [ ] **Step 3: shared/auth/__init__.py 생성**

```python
```
(빈 파일)

- [ ] **Step 4: shared/auth/base.py 생성**

```python
from typing import TypedDict


class AuthUser(TypedDict):
    user_id: str
    roles: list[str]
    allowed_doc_ids: list[str]
```

- [ ] **Step 5: shared/auth/jwt_handler.py 생성**

```python
from datetime import datetime, timedelta, timezone

import jwt


def create_token(
    user_id: str,
    roles: list[str],
    allowed_doc_ids: list[str],
    secret: str,
    expire_minutes: int,
) -> str:
    payload = {
        "sub": user_id,
        "roles": roles,
        "allowed_doc_ids": allowed_doc_ids,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
pytest tests/shared/auth/test_jwt_handler.py -v
```
Expected: 3 passed

- [ ] **Step 7: 커밋**

```bash
git add shared/auth/ tests/shared/auth/
git commit -m "feat(auth): add AuthUser TypedDict and JWT handler"
```

---

## Task 3: FastAPI 인증 엔드포인트 + deps

**Files:**
- Create: `app/api/auth.py`
- Create: `app/api/deps.py`
- Test: `tests/app/api/test_auth.py`

- [ ] **Step 1: 테스트 작성**

`tests/app/api/test_auth.py`:
```python
from fastapi.testclient import TestClient
from app.api.chat import app


def test_login_success():
    res = TestClient(app).post("/auth/token", json={"username": "alice", "password": "alice123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password():
    res = TestClient(app).post("/auth/token", json={"username": "alice", "password": "wrong"})
    assert res.status_code == 401


def test_me_with_valid_token():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "alice", "password": "alice123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user_id"] == "user-alice"


def test_chat_without_token_returns_401():
    res = TestClient(app).post("/chat", json={"question": "테스트"})
    assert res.status_code == 401
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/app/api/test_auth.py -v
```
Expected: FAIL (auth.py, deps.py 없음)

- [ ] **Step 3: app/api/deps.py 생성 (인증 부분만 — Rate Limit은 Task 8에서 추가)**

```python
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from shared.auth.base import AuthUser
from shared.auth.jwt_handler import decode_token
from shared.config import load_config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_config = load_config()


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
    try:
        payload = decode_token(token, secret=_config.jwt_secret)
        return AuthUser(
            user_id=payload["sub"],
            roles=payload["roles"],
            allowed_doc_ids=payload["allowed_doc_ids"],
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if "admin" not in user["roles"]:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
```

> `check_rate_limit`는 Task 8에서 추가한다. Rate Limiter 구현(Task 5) 이후에 deps.py를 수정해야 import 오류가 없다.

- [ ] **Step 4: app/api/auth.py 생성**

```python
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.auth.jwt_handler import create_token
from shared.config import load_config
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

_config = load_config()


def _load_users() -> list[dict]:
    path = Path("config/users.yaml")
    return yaml.safe_load(path.read_text())["users"]


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
def login(req: TokenRequest) -> TokenResponse:
    from fastapi import HTTPException
    users = _load_users()
    user = next(
        (u for u in users if u["username"] == req.username and u["password"] == req.password),
        None,
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(
        user_id=user["user_id"],
        roles=user["roles"],
        allowed_doc_ids=user["allowed_doc_ids"],
        secret=_config.jwt_secret,
        expire_minutes=_config.jwt_expire_minutes,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=dict)
def me(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return dict(current_user)
```

- [ ] **Step 5: app/api/chat.py에 auth 라우터 include (임시)**

`app/api/chat.py`의 `app = FastAPI()` 바로 아래에 추가:

```python
from app.api.auth import router as auth_router
app.include_router(auth_router)
```

전체 `chat.py` (최종 형태 — Task 8에서 한 번 더 수정됨):

```python
import uuid
from functools import lru_cache

from fastapi import FastAPI

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph
from app.api.auth import router as auth_router

from pydantic import BaseModel

app = FastAPI()
app.include_router(auth_router)


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    return build_graph(retriever=retriever, llm=llm)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    thread_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(get_graph(), req.question, config=config)
    return ChatResponse(answer=result.text, sources=result.sources, session_id=thread_id)
```

> `/chat`에 인증 적용은 Task 8에서 한다. 지금은 auth 라우터만 등록.

- [ ] **Step 6: 테스트 실행 — auth 통과, chat_without_token은 Task 8 이후 통과**

```bash
pytest tests/app/api/test_auth.py::test_login_success tests/app/api/test_auth.py::test_login_wrong_password tests/app/api/test_auth.py::test_me_with_valid_token -v
```
Expected: 3 passed (Task 5 완료 후 import 오류 해소)

- [ ] **Step 7: 커밋**

```bash
git add app/api/auth.py app/api/deps.py app/api/chat.py tests/app/api/test_auth.py
git commit -m "feat(auth): add JWT login endpoint and get_current_user dependency"
```

---

## Task 4: AgentState ACL 확장 + VectorStore/Retriever 필터링

**Files:**
- Modify: `app/graph/state.py`
- Modify: `shared/vector_store/base.py`
- Modify: `shared/vector_store/chroma_store.py`
- Modify: `shared/retriever/base.py`
- Modify: `shared/retriever/basic_retriever.py`
- Modify: `app/graph/nodes/retrieve.py`
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: ACL 필터 테스트 추가**

`tests/app/graph/nodes/test_retrieve.py` 끝에 추가:

```python
def test_retrieve_node_passes_allowed_doc_ids():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "질문", "allowed_doc_ids": ["docs/company/policy.md"]},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with(
        "질문", top_k=5, filter_doc_ids=["docs/company/policy.md"]
    )


def test_retrieve_node_passes_empty_filter_when_no_acl():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node({"question": "질문"}, retriever=mock_retriever)

    mock_retriever.retrieve.assert_called_once_with("질문", top_k=5, filter_doc_ids=[])
```

기존 assertion도 `filter_doc_ids=[]` 포함하도록 수정:

```python
def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result("내용", "doc.md")]

    state = {"question": "테스트 질문"}
    result = retrieve_node(state, retriever=mock_retriever)

    assert "documents" in result
    assert len(result["documents"]) == 1
    mock_retriever.retrieve.assert_called_once_with("테스트 질문", top_k=5, filter_doc_ids=[])


def test_retrieve_node_uses_question_field():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node({"question": "특정 질문"}, retriever=mock_retriever)
    mock_retriever.retrieve.assert_called_once_with("특정 질문", top_k=5, filter_doc_ids=[])


def test_retrieve_node_uses_rewritten_question_when_available():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": "재작성 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("재작성 질문", top_k=5, filter_doc_ids=[])


def test_retrieve_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": ""},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("원본 질문", top_k=5, filter_doc_ids=[])
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: 기존 4개 FAIL (assertion 불일치), 신규 2개 FAIL

- [ ] **Step 3: app/graph/state.py 수정**

`AgentState`에 두 필드 추가:

```python
from typing import Literal, TypedDict

from shared.models import SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
    user_id: str           # 추가
    allowed_doc_ids: list[str]  # 추가 — 빈 리스트 = 전체 허용
```

- [ ] **Step 4: shared/vector_store/base.py 수정**

`search()` 시그니처에 `filter_doc_ids` 추가:

```python
from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_doc_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...
```

- [ ] **Step 5: shared/vector_store/chroma_store.py 수정**

`search()`에 `filter_doc_ids` 적용:

```python
import chromadb
from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class ChromaStore(VectorStore):
    def __init__(
        self,
        path: str,
        mode: str = "embedded",
        host: str = "localhost",
        port: int = 8000,
    ) -> None:
        if mode == "http":
            self._client = chromadb.HttpClient(host=host, port=port)
        else:
            self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection("documents")

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{"source": c.source} for c in chunks],
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_doc_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        where = None
        if filter_doc_ids:
            where = {"source": {"$in": filter_doc_ids}}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self._collection.count(), 1)),
            where=where,
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            chunk = Chunk(
                text=doc,
                source=results["metadatas"][0][i]["source"],
                chunk_id=results["ids"][0][i],
            )
            score = 1.0 - results["distances"][0][i]
            output.append(SearchResult(chunk=chunk, score=score))
        return output

    def count(self) -> int:
        return self._collection.count()
```

- [ ] **Step 6: shared/retriever/base.py 수정**

```python
from abc import ABC, abstractmethod

from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 5, filter_doc_ids: list[str] | None = None
    ) -> list[SearchResult]: ...
```

- [ ] **Step 7: shared/retriever/basic_retriever.py 수정**

```python
from shared.embedder.base import Embedder
from shared.models import SearchResult
from shared.retriever.base import Retriever
from shared.vector_store.base import VectorStore


class BasicRetriever(Retriever):
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def retrieve(
        self, query: str, top_k: int = 5, filter_doc_ids: list[str] | None = None
    ) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k, filter_doc_ids=filter_doc_ids)
```

- [ ] **Step 8: app/graph/nodes/retrieve.py 수정**

```python
from shared.models import SearchResult
from shared.retriever.base import Retriever


def retrieve_node(state: dict, *, retriever: Retriever) -> dict:
    query = state.get("rewritten_question") or state["question"]
    allowed_doc_ids = state.get("allowed_doc_ids", [])
    results: list[SearchResult] = retriever.retrieve(
        query, top_k=5, filter_doc_ids=allowed_doc_ids
    )
    return {"documents": results}
```

- [ ] **Step 9: app/graph/builder.py 수정 — answer_question() 파라미터 추가**

`answer_question()` 함수 시그니처와 `initial` dict 수정:

```python
def answer_question(
    graph: CompiledStateGraph,
    question: str,
    config: dict | None = None,
    user_id: str = "anonymous",
    allowed_doc_ids: list[str] | None = None,
) -> Answer:
    config = _ensure_thread_id(config)
    existing = graph.get_state(config)
    chat_history = (existing.values or {}).get("chat_history", [])

    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": user_id,
        "allowed_doc_ids": allowed_doc_ids or [],
    }
    final = graph.invoke(initial, config=config)
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 10: 테스트 실행 — 통과 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: 6 passed

- [ ] **Step 11: 전체 단위 테스트 확인**

```bash
pytest tests/ -v --ignore=tests/load --ignore=tests/eval -x
```
Expected: all passed (기존 회귀 없음)

- [ ] **Step 12: 커밋**

```bash
git add app/graph/state.py shared/vector_store/base.py shared/vector_store/chroma_store.py \
        shared/retriever/base.py shared/retriever/basic_retriever.py \
        app/graph/nodes/retrieve.py app/graph/builder.py \
        tests/app/graph/nodes/test_retrieve.py
git commit -m "feat(acl): add allowed_doc_ids filter to retrieve pipeline"
```

---

## Task 5: Rate Limiter

**Files:**
- Create: `shared/rate_limiter/__init__.py`
- Create: `shared/rate_limiter/base.py`
- Create: `shared/rate_limiter/in_memory.py`
- Test: `tests/shared/rate_limiter/test_in_memory.py`

- [ ] **Step 1: 테스트 작성**

`tests/shared/rate_limiter/test_in_memory.py`:
```python
import time
from shared.rate_limiter.in_memory import InMemoryRateLimiter


def test_allows_under_limit():
    limiter = InMemoryRateLimiter(rules={"/chat": 3}, default_limit=3)
    for _ in range(3):
        assert limiter.is_allowed("user-1", "/chat") is True


def test_blocks_over_limit():
    limiter = InMemoryRateLimiter(rules={"/chat": 3}, default_limit=3)
    for _ in range(3):
        limiter.is_allowed("user-1", "/chat")
    assert limiter.is_allowed("user-1", "/chat") is False


def test_different_users_are_independent():
    limiter = InMemoryRateLimiter(rules={"/chat": 1}, default_limit=1)
    limiter.is_allowed("user-1", "/chat")
    assert limiter.is_allowed("user-2", "/chat") is True


def test_uses_default_limit_for_unknown_endpoint():
    limiter = InMemoryRateLimiter(rules={}, default_limit=2)
    limiter.is_allowed("user-1", "/other")
    limiter.is_allowed("user-1", "/other")
    assert limiter.is_allowed("user-1", "/other") is False
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/shared/rate_limiter/test_in_memory.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 구현 파일 생성**

`shared/rate_limiter/__init__.py` (빈 파일):
```python
```

`shared/rate_limiter/base.py`:
```python
from abc import ABC, abstractmethod


class RateLimiter(ABC):
    @abstractmethod
    def is_allowed(self, user_id: str, endpoint: str) -> bool: ...
```

`shared/rate_limiter/in_memory.py`:
```python
import time
from collections import defaultdict, deque

from shared.rate_limiter.base import RateLimiter


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, rules: dict[str, int], default_limit: int = 20) -> None:
        self._rules = rules
        self._default_limit = default_limit
        self._windows: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, user_id: str, endpoint: str) -> bool:
        limit = self._rules.get(endpoint, self._default_limit)
        key = f"{user_id}:{endpoint}"
        now = time.monotonic()
        window = self._windows[key]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
pytest tests/shared/rate_limiter/test_in_memory.py -v
```
Expected: 4 passed

- [ ] **Step 5: Task 3 테스트 재실행 (import 오류 해소 확인)**

```bash
pytest tests/app/api/test_auth.py::test_login_success tests/app/api/test_auth.py::test_login_wrong_password tests/app/api/test_auth.py::test_me_with_valid_token -v
```
Expected: 3 passed

- [ ] **Step 6: 커밋**

```bash
git add shared/rate_limiter/ tests/shared/rate_limiter/
git commit -m "feat(rate-limiter): add in-memory sliding window rate limiter"
```

---

## Task 6: 비용 모니터링 (Sink 패턴)

**Files:**
- Create: `shared/observability/sinks/__init__.py`
- Create: `shared/observability/sinks/base.py`
- Create: `shared/observability/sinks/file_sink.py`
- Create: `shared/observability/cost_tracker.py`
- Modify: `app/graph/nodes/generate.py`
- Test: `tests/shared/observability/test_cost_tracker.py`

- [ ] **Step 1: 테스트 작성**

`tests/shared/observability/test_cost_tracker.py`:
```python
from unittest.mock import MagicMock
from shared.observability.cost_tracker import CostTracker
from shared.observability.sinks.base import CostSink


def _make_sink() -> CostSink:
    return MagicMock(spec=CostSink)


def test_track_calls_all_sinks():
    sink1, sink2 = _make_sink(), _make_sink()
    tracker = CostTracker(sinks=[sink1, sink2])
    tracker.track("user-1", input_tokens=100, output_tokens=50, model="gpt-4o-mini")
    sink1.record.assert_called_once()
    sink2.record.assert_called_once()


def test_track_calculates_cost_for_gpt4o_mini():
    sink = _make_sink()
    tracker = CostTracker(sinks=[sink])
    tracker.track("user-1", input_tokens=1_000_000, output_tokens=0, model="gpt-4o-mini")
    _, kwargs = sink.record.call_args
    # gpt-4o-mini input: $0.15 per 1M tokens
    assert abs(sink.record.call_args[1]["cost_usd"] - 0.15) < 0.001 or \
           abs(sink.record.call_args[0][3] - 0.15) < 0.001


def test_track_with_no_sinks_does_not_raise():
    tracker = CostTracker(sinks=[])
    tracker.track("user-1", input_tokens=100, output_tokens=50, model="gpt-4o-mini")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/shared/observability/test_cost_tracker.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Sink 파일 생성**

`shared/observability/sinks/__init__.py` (빈 파일):
```python
```

`shared/observability/sinks/base.py`:
```python
from abc import ABC, abstractmethod


class CostSink(ABC):
    @abstractmethod
    def record(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
    ) -> None: ...
```

`shared/observability/sinks/file_sink.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

from shared.observability.sinks.base import CostSink


class FileSink(CostSink):
    def __init__(self, log_dir: str = "logs") -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(exist_ok=True)

    def record(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
    ) -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._dir / f"cost_{date}.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
            "model": model,
        }
        with path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: CostTracker 생성**

`shared/observability/cost_tracker.py`:
```python
from shared.observability.sinks.base import CostSink

_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
}

_tracker: "CostTracker | None" = None


class CostTracker:
    def __init__(self, sinks: list[CostSink]) -> None:
        self._sinks = sinks

    def track(
        self, user_id: str, input_tokens: int, output_tokens: int, model: str
    ) -> None:
        pricing = _MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
        for sink in self._sinks:
            sink.record(user_id, input_tokens, output_tokens, cost, model)


def init_tracker(sinks: list[CostSink]) -> None:
    global _tracker
    _tracker = CostTracker(sinks)


def get_tracker() -> "CostTracker | None":
    return _tracker
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
pytest tests/shared/observability/test_cost_tracker.py -v
```
Expected: 3 passed

- [ ] **Step 6: generate_node에 cost tracking 추가**

`app/graph/nodes/generate.py`:
```python
from shared.llm.base import LLMClient
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    history = state.get("chat_history", [])
    history_text = (
        "\n".join(f"{m['role']}: {m['content']}" for m in history) if history else "없음"
    )
    prompt = RAG_GENERATE.format(
        context=context, question=question, chat_history=history_text
    )
    text = llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        input_tokens = len(prompt) // 4
        output_tokens = len(text) // 4
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="unknown",
        )

    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
```

- [ ] **Step 7: app/api/chat.py에 tracker 초기화 추가**

`chat.py` 상단 import 다음에 추가:

```python
from shared.observability.cost_tracker import init_tracker
from shared.observability.sinks.file_sink import FileSink

init_tracker([FileSink("logs")])
```

- [ ] **Step 8: generate_node 기존 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_generate.py -v
```
Expected: all passed (tracker=None이면 skip하므로 기존 테스트 영향 없음)

- [ ] **Step 9: 커밋**

```bash
git add shared/observability/sinks/ shared/observability/cost_tracker.py \
        app/graph/nodes/generate.py app/api/chat.py \
        tests/shared/observability/test_cost_tracker.py
git commit -m "feat(cost): add CostTracker with FileSink, track usage in generate_node"
```

---

## Task 7: 어드민 API

**Files:**
- Create: `app/api/admin.py`
- Modify: `app/api/chat.py`
- Test: `tests/app/api/test_admin.py`

- [ ] **Step 1: 테스트 작성**

`tests/app/api/test_admin.py`:
```python
from fastapi.testclient import TestClient
from app.api.chat import app


def _admin_token(client: TestClient) -> str:
    return client.post(
        "/auth/token", json={"username": "admin", "password": "admin123"}
    ).json()["access_token"]


def _user_token(client: TestClient) -> str:
    return client.post(
        "/auth/token", json={"username": "alice", "password": "alice123"}
    ).json()["access_token"]


def test_admin_index_status_requires_admin():
    client = TestClient(app)
    token = _user_token(client)
    res = client.get("/admin/index/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_admin_index_status_returns_count():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/index/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "chunk_count" in data


def test_admin_users_returns_list():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_admin_cost_report_returns_list():
    client = TestClient(app)
    token = _admin_token(client)
    res = client.get("/admin/cost/report", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/app/api/test_admin.py -v
```
Expected: FAIL (admin.py 없음)

- [ ] **Step 3: app/api/admin.py 생성**

```python
import json
from datetime import date, timedelta
from pathlib import Path

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.vector_store.factory import create_vector_store
from app.api.deps import require_admin
from shared.auth.base import AuthUser
from app.ingestion.indexer import build_index

router = APIRouter(prefix="/admin", tags=["admin"])

_config = load_config()


@router.get("/index/status")
def index_status(_: AuthUser = Depends(require_admin)) -> dict:
    store = create_vector_store(_config)
    return {"chunk_count": store.count()}


@router.post("/index/rebuild", status_code=202)
def index_rebuild(
    background_tasks: BackgroundTasks,
    _: AuthUser = Depends(require_admin),
) -> dict:
    background_tasks.add_task(build_index, "docs/company")
    return {"status": "rebuilding"}


@router.post("/eval/run")
def eval_run(_: AuthUser = Depends(require_admin)) -> dict:
    import subprocess
    result = subprocess.run(
        ["python", "tests/eval/runner.py"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {"stdout": result.stdout, "returncode": result.returncode}


@router.get("/eval/results")
def eval_results(_: AuthUser = Depends(require_admin)) -> list:
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    results = []
    for f in sorted(log_dir.glob("eval_*.jsonl"), reverse=True)[:10]:
        for line in f.read_text().splitlines():
            results.append(json.loads(line))
    return results


@router.get("/cost/report")
def cost_report(
    target_date: str = Query(default=None, description="YYYY-MM-DD, 기본값: 오늘"),
    _: AuthUser = Depends(require_admin),
) -> list:
    if target_date is None:
        target_date = date.today().isoformat()
    path = Path(f"logs/cost_{target_date}.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@router.get("/users")
def list_users(_: AuthUser = Depends(require_admin)) -> list:
    path = Path("config/users.yaml")
    users = yaml.safe_load(path.read_text())["users"]
    return [
        {
            "user_id": u["user_id"],
            "username": u["username"],
            "roles": u["roles"],
            "allowed_doc_ids": u["allowed_doc_ids"],
        }
        for u in users
    ]


@router.put("/users/{user_id}/docs")
def update_user_docs(
    user_id: str,
    allowed_doc_ids: list[str],
    _: AuthUser = Depends(require_admin),
) -> dict:
    path = Path("config/users.yaml")
    data = yaml.safe_load(path.read_text())
    for user in data["users"]:
        if user["user_id"] == user_id:
            user["allowed_doc_ids"] = allowed_doc_ids
            path.write_text(yaml.dump(data, allow_unicode=True))
            return {"user_id": user_id, "allowed_doc_ids": allowed_doc_ids}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="User not found")
```

- [ ] **Step 4: app/api/chat.py에 admin 라우터 include**

`app.include_router(auth_router)` 바로 다음에 추가:

```python
from app.api.admin import router as admin_router
app.include_router(admin_router)
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
pytest tests/app/api/test_admin.py -v
```
Expected: 4 passed

- [ ] **Step 6: 커밋**

```bash
git add app/api/admin.py app/api/chat.py tests/app/api/test_admin.py
git commit -m "feat(admin): add admin API endpoints for index, eval, cost, users"
```

---

## Task 8: /chat 인증 + Rate Limiting 적용

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/chat.py`

- [ ] **Step 1: deps.py에 check_rate_limit 추가 (Task 5 완료 후)**

`app/api/deps.py` 상단 import에 추가:
```python
from fastapi import Depends, HTTPException, Request
from shared.rate_limiter.in_memory import InMemoryRateLimiter
```

`_config = load_config()` 다음에 추가:
```python
_rate_limiter = InMemoryRateLimiter(
    rules={"/chat": _config.rate_limit_per_minute},
    default_limit=_config.rate_limit_per_minute,
)
```

파일 끝에 함수 추가:
```python
def check_rate_limit(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> None:
    if not _rate_limiter.is_allowed(user["user_id"], request.url.path):
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": "60"},
        )
```

- [ ] **Step 2: /chat 엔드포인트에 인증 + Rate Limiting 적용**

`app/api/chat.py`의 `chat()` 함수를 수정:

```python
from app.api.deps import get_current_user, check_rate_limit
from shared.auth.base import AuthUser

@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    thread_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(
        get_graph(),
        req.question,
        config=config,
        user_id=current_user["user_id"],
        allowed_doc_ids=current_user["allowed_doc_ids"],
    )
    return ChatResponse(answer=result.text, sources=result.sources, session_id=thread_id)
```

- [ ] **Step 3: 인증 없는 /chat 요청이 401 반환하는지 확인**

```bash
pytest tests/app/api/test_auth.py::test_chat_without_token_returns_401 -v
```
Expected: PASS

- [ ] **Step 4: 전체 API 테스트 확인**

```bash
pytest tests/app/api/ -v
```
Expected: all passed

- [ ] **Step 5: 커밋**

```bash
git add app/api/deps.py app/api/chat.py
git commit -m "feat(auth): require JWT auth and rate limit on /chat endpoint"
```

---

## Task 9: Locust 부하 테스트

**Files:**
- Create: `tests/load/locustfile.py`

- [ ] **Step 1: tests/load/ 디렉터리 생성 + locustfile.py 작성**

`tests/load/locustfile.py`:
```python
import random
from locust import HttpUser, between, task

DOC_SEARCH_QUESTIONS = [
    "연차 신청은 어떻게 하나요?",
    "온보딩 절차를 알려주세요",
    "사내 보안 정책이 궁금합니다",
    "팀 구성원은 어떻게 되나요?",
    "복리후생 혜택을 알려주세요",
]

WEB_SEARCH_QUESTIONS = [
    "최근 LangGraph 업데이트 내용 알려줘",
    "FastAPI 최신 버전은?",
    "Python 3.12 새로운 기능은?",
]


class ChatUser(HttpUser):
    wait_time = between(1, 3)
    token: str = ""

    def on_start(self) -> None:
        res = self.client.post(
            "/auth/token",
            json={"username": "alice", "password": "alice123"},
        )
        self.token = res.json().get("access_token", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(7)
    def chat_doc_search(self) -> None:
        self.client.post(
            "/chat",
            json={"question": random.choice(DOC_SEARCH_QUESTIONS)},
            headers=self._headers(),
            name="/chat [doc_search]",
        )

    @task(2)
    def chat_web_search(self) -> None:
        self.client.post(
            "/chat",
            json={"question": random.choice(WEB_SEARCH_QUESTIONS)},
            headers=self._headers(),
            name="/chat [web_search]",
        )

    @task(1)
    def admin_cost_report(self) -> None:
        # admin 계정으로 별도 요청 (alice는 admin 권한 없음)
        pass


class AdminUser(HttpUser):
    wait_time = between(5, 10)
    token: str = ""

    def on_start(self) -> None:
        res = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )
        self.token = res.json().get("access_token", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task
    def cost_report(self) -> None:
        self.client.get(
            "/admin/cost/report",
            headers=self._headers(),
            name="/admin/cost/report",
        )
```

- [ ] **Step 2: 서버 실행 후 Locust 웹 UI 확인 (수동)**

```bash
# 터미널 1: 서버 실행
uvicorn app.api.chat:app --reload

# 터미널 2: Locust 실행
locust -f tests/load/locustfile.py --host=http://localhost:8000
# 브라우저 http://localhost:8089 접속 → Users: 10, Spawn rate: 2로 시작
```

Expected: 에러율 < 1%, 응답시간 P95 < 10s

- [ ] **Step 3: Headless CI 실행 검증**

```bash
# 서버가 실행 중인 상태에서
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --users 10 --spawn-rate 2 --run-time 30s --headless
```

Expected: 오류 없이 종료, 통계 출력

- [ ] **Step 4: 커밋**

```bash
git add tests/load/
git commit -m "test(load): add Locust load test scenarios for /chat and /admin"
```

---

## Task 10: 전체 회귀 테스트 + DoD 확인

- [ ] **Step 1: 전체 단위 테스트 실행**

```bash
pytest tests/ --ignore=tests/load --ignore=tests/eval -v
```
Expected: all passed

- [ ] **Step 2: 평가셋 회귀 테스트 실행**

```bash
python tests/eval/runner.py
```
Expected: doc_search recall@5 ≥ 0.80 (Phase 4 기준 유지)

- [ ] **Step 3: DoD 체크리스트 확인**

```
- [ ] JWT 인증 단위 테스트 — tests/shared/auth/test_jwt_handler.py PASS
- [ ] Rate limiting 단위 테스트 (429 응답) — tests/shared/rate_limiter/test_in_memory.py PASS
- [ ] 어드민 role 검증 테스트 (403) — tests/app/api/test_admin.py PASS
- [ ] 비인가 문서 노출 0건 — ACL filter 단위 테스트 PASS
- [ ] 일일 비용 리포트 — /admin/cost/report 엔드포인트 + logs/cost_YYYY-MM-DD.jsonl 생성 확인
- [ ] 동시 50명 부하 테스트 — Locust --users 50 수동 실행 후 P95 < 10s, 에러율 < 1% 확인
- [ ] 회귀 테스트 — recall@5 ≥ 0.80 유지
```

- [ ] **Step 4: PR 생성**

```bash
git push origin feat/phase-5
gh pr create --title "feat: Phase 5 — production readiness" --body "$(cat <<'EOF'
## DoD
- [ ] JWT 인증 단위 테스트 PASS
- [ ] Rate limiting 단위 테스트 PASS
- [ ] 어드민 role 검증 (403) PASS
- [ ] 비인가 문서 노출 0건 (ACL filter 테스트 PASS)
- [ ] 일일 비용 리포트 자동화 (/admin/cost/report)
- [ ] 동시 50명 부하 테스트 통과 (P95 < 10s, 에러율 < 1%)
- [ ] 회귀 테스트 recall@5 ≥ 0.80 유지
EOF
)"
```

- [ ] **Step 5: merge 후 태그**

```bash
git tag phase-5
git push origin phase-5
```
