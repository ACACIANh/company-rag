# Access Control (OpenFGA + Chroma Pre-filter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenFGA 기반 ABAC/RBAC 권한 제어를 RAG 파이프라인에 통합한다. 2-tier pre-filter(team_id+sensitivity / personal_doc_ids)로 Chroma 검색을 제한하고, PostgreSQL TTL 캐시로 OpenFGA 호출 횟수를 줄인다.

**Architecture:** `shared/fga/` 모듈이 `PermissionCacheBackend` ABC + `FGAClient`를 제공한다. `permission_node`가 `doc_search` 경로 진입 시 권한을 조회해 `AgentState`에 넣고, `retrieve_node`가 이를 읽어 Chroma `where` 필터를 구성한다. 문서 등록 시 Indexer가 OpenFGA tuple을 기록하고, Admin API가 입퇴사/팀이동/개인공유를 처리한다.

**Tech Stack:** `openfga-sdk` (OpenFGA Python SDK), `psycopg2-binary` (PostgreSQL), `chromadb`, `langgraph`, `fastapi`

---

## 파일 맵

| 파일 | 생성/수정 | 역할 |
|---|---|---|
| `shared/fga/__init__.py` | 생성 | 패키지 |
| `shared/fga/models.py` | 생성 | `UserPermission`, `FGAConfig` dataclass |
| `shared/fga/base.py` | 생성 | `PermissionCacheBackend` ABC |
| `shared/fga/sensitivity.py` | 생성 | `detect_sensitivity(text)` 순수 함수 |
| `shared/fga/client.py` | 생성 | `FGAClient` — OpenFGA 래퍼 + `build_chroma_filter()` |
| `shared/fga/cache/__init__.py` | 생성 | 패키지 |
| `shared/fga/cache/memory.py` | 생성 | `InMemoryCacheBackend` (TTL 기반) |
| `shared/fga/cache/postgres.py` | 생성 | `PostgresCacheBackend` |
| `shared/config.py` | 수정 | FGA 관련 필드 5개 추가 |
| `shared/vector_store/base.py` | 수정 | `search()` — `filter_doc_ids` → `where_filter: dict\|None` |
| `shared/vector_store/chroma_store.py` | 수정 | `where_filter` 직접 전달 + metadata에 `team_id`, `sensitivity`, `document_id` 지원 |
| `shared/retriever/base.py` | 수정 | `retrieve()` — `filter_doc_ids` → `where_filter: dict\|None` |
| `shared/retriever/basic_retriever.py` | 수정 | `where_filter` 전달 |
| `shared/indexer/indexer.py` | 수정 | `FGAClient` DI 추가, metadata에 `team_id`, `sensitivity`, `document_id` 포함 |
| `app/graph/state.py` | 수정 | `user_teams: list[str]`, `personal_doc_ids: list[str]` 필드 추가 |
| `app/graph/nodes/permission.py` | 생성 | `permission_node` |
| `app/graph/nodes/retrieve.py` | 수정 | `FGAClient` 주입, `build_chroma_filter()` 사용 |
| `app/graph/builder.py` | 수정 | `permission_node` 연결, `fga_client` 파라미터 추가 |
| `app/ingestion/indexer.py` | 수정 | `FGAClient` 생성 후 `Indexer`에 전달 |
| `app/api/admin.py` | 수정 | FGA 팀/문서 관리 엔드포인트 5개 추가 |
| `tests/shared/fga/__init__.py` | 생성 | 패키지 |
| `tests/shared/fga/test_sensitivity.py` | 생성 | `detect_sensitivity()` 단위 테스트 |
| `tests/shared/fga/test_memory_cache.py` | 생성 | `InMemoryCacheBackend` TTL/invalidate 테스트 |
| `tests/shared/fga/test_client.py` | 생성 | `build_chroma_filter()` + `get_permission()` 단위 테스트 |
| `tests/shared/fga/test_postgres_cache.py` | 생성 | `PostgresCacheBackend` 통합 테스트 (PG 픽스처) |
| `tests/app/graph/nodes/test_permission_node.py` | 생성 | `permission_node` 단위 테스트 |
| `tests/app/graph/nodes/test_retrieve.py` | 수정 | `where_filter` 기반으로 assertion 변경 |
| `tests/app/test_rag_with_fga.py` | 생성 | FGA 통합 시나리오 테스트 |

---

## Task 1: Config — FGA 필드 추가

**Files:**
- Modify: `shared/config.py`
- Modify: `tests/shared/test_config.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_config.py`에 아래 테스트를 추가한다.

```python
def test_config_fga_defaults(monkeypatch):
    for key in ["FGA_API_URL", "FGA_STORE_ID", "FGA_API_KEY",
                "FGA_CACHE_BACKEND", "FGA_CACHE_TTL_SECONDS"]:
        monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.fga_api_url == "http://localhost:8080"
    assert config.fga_store_id == ""
    assert config.fga_api_key == ""
    assert config.fga_cache_backend == "memory"
    assert config.fga_cache_ttl_seconds == 60
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_config.py::test_config_fga_defaults -v
```
Expected: `AttributeError: 'Config' object has no attribute 'fga_api_url'`

- [ ] **Step 3: Config 필드 추가**

`shared/config.py`의 `Config` dataclass에 아래 필드를 추가한다.

```python
@dataclass
class Config:
    # ... 기존 필드 유지 ...
    fga_api_url:           str
    fga_store_id:          str
    fga_api_key:           str
    fga_cache_backend:     str   # "postgres" | "memory"
    fga_cache_ttl_seconds: int
```

`load_config()`에 아래를 추가한다.

```python
def load_config() -> Config:
    return Config(
        # ... 기존 항목 유지 ...
        fga_api_url=os.getenv("FGA_API_URL", "http://localhost:8080"),
        fga_store_id=os.getenv("FGA_STORE_ID", ""),
        fga_api_key=os.getenv("FGA_API_KEY", ""),
        fga_cache_backend=os.getenv("FGA_CACHE_BACKEND", "memory"),
        fga_cache_ttl_seconds=int(os.getenv("FGA_CACHE_TTL_SECONDS", "60")),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_config.py -v
```
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/config.py tests/shared/test_config.py
git commit -m "feat(config): FGA 설정 필드 5개 추가"
```

---

## Task 2: `shared/fga/` — 모델 및 ABC

**Files:**
- Create: `shared/fga/__init__.py`
- Create: `shared/fga/models.py`
- Create: `shared/fga/base.py`
- Create: `shared/fga/cache/__init__.py`
- Create: `tests/shared/fga/__init__.py`

- [ ] **Step 1: 디렉터리 및 파일 생성**

```bash
mkdir -p shared/fga/cache tests/shared/fga
touch shared/fga/__init__.py shared/fga/cache/__init__.py tests/shared/fga/__init__.py
```

- [ ] **Step 2: `shared/fga/models.py` 작성**

```python
from dataclasses import dataclass, field


@dataclass
class UserPermission:
    user_id: str
    teams: list[str] = field(default_factory=list)
    personal_docs: list[str] = field(default_factory=list)


@dataclass
class FGAConfig:
    api_url: str
    store_id: str
    api_key: str = ""
    cache_ttl_seconds: int = 60
    pg_dsn: str = ""   # 설정 시 personal_docs를 user_doc_grants 테이블에서 조회
```

- [ ] **Step 3: `shared/fga/base.py` 작성**

```python
from abc import ABC, abstractmethod
from shared.fga.models import UserPermission


class PermissionCacheBackend(ABC):
    @abstractmethod
    def get(self, user_id: str) -> UserPermission | None: ...

    @abstractmethod
    def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None: ...

    @abstractmethod
    def invalidate(self, user_id: str) -> None: ...
```

- [ ] **Step 4: import 확인**

```bash
python -c "from shared.fga.models import UserPermission, FGAConfig; from shared.fga.base import PermissionCacheBackend; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/ tests/shared/fga/__init__.py
git commit -m "feat(fga): UserPermission/FGAConfig 모델 및 PermissionCacheBackend ABC 추가"
```

---

## Task 3: `shared/fga/sensitivity.py` — 민감도 자동 감지

**Files:**
- Create: `shared/fga/sensitivity.py`
- Create: `tests/shared/fga/test_sensitivity.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/fga/test_sensitivity.py`를 작성한다.

```python
import pytest
from shared.fga.sensitivity import detect_sensitivity


@pytest.mark.parametrize("text,expected", [
    ("2024년 연봉 협상 결과", "secret"),
    ("인사 평가 Q3 결과", "secret"),
    ("기밀 프로젝트 계획서", "secret"),
    ("급여 명세서 2024", "secret"),
    ("내부 공지 — draft 버전", "internal"),
    ("INTERNAL USE ONLY", "internal"),
    ("신제품 발표 자료", "public"),
    ("회사 소개 페이지", "public"),
    ("", "public"),
])
def test_detect_sensitivity(text, expected):
    assert detect_sensitivity(text) == expected
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_sensitivity.py -v
```
Expected: `ModuleNotFoundError: No module named 'shared.fga.sensitivity'`

- [ ] **Step 3: `shared/fga/sensitivity.py` 작성**

```python
_SECRET_KEYWORDS = ["기밀", "급여", "인사", "연봉", "평가"]
_INTERNAL_KEYWORDS = ["내부", "draft", "internal"]


def detect_sensitivity(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in _SECRET_KEYWORDS):
        return "secret"
    if any(k in lower for k in _INTERNAL_KEYWORDS):
        return "internal"
    return "public"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_sensitivity.py -v
```
Expected: 9개 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/sensitivity.py tests/shared/fga/test_sensitivity.py
git commit -m "feat(fga): detect_sensitivity() 순수 함수 추가"
```

---

## Task 4: `shared/fga/cache/memory.py` — InMemoryCacheBackend

**Files:**
- Create: `shared/fga/cache/memory.py`
- Create: `tests/shared/fga/test_memory_cache.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/fga/test_memory_cache.py`를 작성한다.

```python
import time
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.models import UserPermission


def _perm(user_id="u1") -> UserPermission:
    return UserPermission(user_id=user_id, teams=["team:dev"], personal_docs=["doc:secret"])


def test_set_and_get_returns_permission():
    cache = InMemoryCacheBackend()
    perm = _perm()
    cache.set("u1", perm, ttl_seconds=60)
    result = cache.get("u1")
    assert result is not None
    assert result.teams == ["team:dev"]
    assert result.personal_docs == ["doc:secret"]


def test_get_returns_none_for_unknown_user():
    cache = InMemoryCacheBackend()
    assert cache.get("unknown") is None


def test_ttl_expiry_returns_none():
    cache = InMemoryCacheBackend()
    cache.set("u1", _perm(), ttl_seconds=1)
    time.sleep(1.1)
    assert cache.get("u1") is None


def test_invalidate_removes_entry():
    cache = InMemoryCacheBackend()
    cache.set("u1", _perm(), ttl_seconds=60)
    cache.invalidate("u1")
    assert cache.get("u1") is None


def test_invalidate_nonexistent_is_noop():
    cache = InMemoryCacheBackend()
    cache.invalidate("ghost")  # should not raise
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_memory_cache.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: `shared/fga/cache/memory.py` 작성**

```python
import time
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class InMemoryCacheBackend(PermissionCacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[UserPermission, float]] = {}

    def get(self, user_id: str) -> UserPermission | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        perm, expires_at = entry
        if time.time() > expires_at:
            del self._store[user_id]
            return None
        return perm

    def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        self._store[user_id] = (perm, time.time() + ttl_seconds)

    def invalidate(self, user_id: str) -> None:
        self._store.pop(user_id, None)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_memory_cache.py -v
```
Expected: 5개 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/cache/memory.py tests/shared/fga/test_memory_cache.py
git commit -m "feat(fga): InMemoryCacheBackend TTL 캐시 구현"
```

---

## Task 5: `shared/fga/client.py` — `build_chroma_filter()` (순수 함수 파트)

**Files:**
- Create: `shared/fga/client.py`
- Create: `tests/shared/fga/test_client.py` (build_chroma_filter 테스트)

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/fga/test_client.py`를 작성한다.

```python
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.fga.cache.memory import InMemoryCacheBackend


def _client() -> FGAClient:
    config = FGAConfig(api_url="http://localhost:8080", store_id="test-store")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def test_build_chroma_filter_public_only():
    """팀도 개인문서도 없으면 public 문서만 반환."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    result = client.build_chroma_filter(perm)
    assert result == {"sensitivity": "public"}


def test_build_chroma_filter_with_teams():
    """팀이 있으면 public + internal(팀 필터) 포함."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev", "team:ops"], personal_docs=[])
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"team_id": {"$in": ["team:dev", "team:ops"]}}, {"sensitivity": "internal"}]},
        ]
    }


def test_build_chroma_filter_with_personal_docs():
    """개인 문서가 있으면 secret 조건 포함."""
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"sensitivity": "secret"}, {"document_id": {"$in": ["doc:salary"]}}]},
        ]
    }


def test_build_chroma_filter_full():
    """팀 + 개인 문서 모두 있으면 세 조건 모두 포함."""
    client = _client()
    perm = UserPermission(
        user_id="u1",
        teams=["team:dev"],
        personal_docs=["doc:review"],
    )
    result = client.build_chroma_filter(perm)
    assert result == {
        "$or": [
            {"sensitivity": "public"},
            {"$and": [{"team_id": {"$in": ["team:dev"]}}, {"sensitivity": "internal"}]},
            {"$and": [{"sensitivity": "secret"}, {"document_id": {"$in": ["doc:review"]}}]},
        ]
    }
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'shared.fga.client'`

- [ ] **Step 3: `shared/fga/client.py` 작성 (build_chroma_filter만)**

```python
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


class FGAClient:
    def __init__(self, config: FGAConfig, cache: PermissionCacheBackend) -> None:
        self._config = config
        self._cache = cache

    def build_chroma_filter(self, perm: UserPermission) -> dict:
        clauses: list[dict] = [{"sensitivity": "public"}]
        if perm.teams:
            clauses.append({
                "$and": [
                    {"team_id": {"$in": perm.teams}},
                    {"sensitivity": "internal"},
                ]
            })
        if perm.personal_docs:
            clauses.append({
                "$and": [
                    {"sensitivity": "secret"},
                    {"document_id": {"$in": perm.personal_docs}},
                ]
            })
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}

    def get_permission(self, user_id: str) -> UserPermission:
        raise NotImplementedError("Task 6에서 구현")

    def write_tuples(
        self, doc_id: str, owner_id: str, team_id: str, sensitivity: str
    ) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def delete_user_tuples(self, user_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_client.py -v
```
Expected: 4개 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/client.py tests/shared/fga/test_client.py
git commit -m "feat(fga): FGAClient.build_chroma_filter() 순수 함수 구현"
```

---

## Task 6: `shared/fga/client.py` — `get_permission()` + FGA 연동

**Files:**
- Modify: `shared/fga/client.py`
- Modify: `tests/shared/fga/test_client.py`

> `get_permission()`은 OpenFGA API를 호출한다. 테스트에서는 FGA 호출 부분을 mock한다.

- [ ] **Step 1: 추가 테스트 작성**

`tests/shared/fga/test_client.py` 맨 아래에 추가한다.

```python
from unittest.mock import patch


def test_get_permission_returns_cached():
    """캐시 히트 시 FGA API 호출 없이 반환."""
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_fetch_from_fga") as mock_fetch:
        result = client.get_permission("u1")

    mock_fetch.assert_not_called()
    assert result.teams == ["team:dev"]


def test_get_permission_calls_fga_on_cache_miss():
    """캐시 미스 시 _fetch_from_fga 호출 후 캐시에 저장."""
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)
    expected = UserPermission(user_id="u2", teams=["team:hr"], personal_docs=["doc:eval"])

    with patch.object(client, "_fetch_from_fga", return_value=expected):
        result = client.get_permission("u2")

    assert result.teams == ["team:hr"]
    cached = cache.get("u2")
    assert cached is not None
    assert cached.teams == ["team:hr"]


def test_write_tuples_invalidates_cache():
    """write_tuples 후 owner의 캐시가 무효화된다."""
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="owner1", teams=["team:dev"], personal_docs=[])
    cache.set("owner1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_write_fga_tuples"):
        client.write_tuples("doc:x", "owner1", "team:dev", "internal")

    assert cache.get("owner1") is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_client.py::test_get_permission_returns_cached -v
```
Expected: `NotImplementedError`

- [ ] **Step 3: `shared/fga/client.py`에 `get_permission()` 구현**

기존 `client.py` 전체를 아래로 교체한다.

```python
import asyncio
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


class FGAClient:
    def __init__(self, config: FGAConfig, cache: PermissionCacheBackend) -> None:
        self._config = config
        self._cache = cache

    # ── 순수 함수 ────────────────────────────────────────────
    def build_chroma_filter(self, perm: UserPermission) -> dict:
        clauses: list[dict] = [{"sensitivity": "public"}]
        if perm.teams:
            clauses.append({
                "$and": [
                    {"team_id": {"$in": perm.teams}},
                    {"sensitivity": "internal"},
                ]
            })
        if perm.personal_docs:
            clauses.append({
                "$and": [
                    {"sensitivity": "secret"},
                    {"document_id": {"$in": perm.personal_docs}},
                ]
            })
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}

    # ── 캐시 + FGA 연동 ───────────────────────────────────────
    def get_permission(self, user_id: str) -> UserPermission:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached
        perm = self._fetch_from_fga(user_id)
        self._cache.set(user_id, perm, self._config.cache_ttl_seconds)
        return perm

    def _fetch_from_fga(self, user_id: str) -> UserPermission:
        # 팀: OpenFGA listObjects (짧은 목록)
        teams = self._list_fga_objects(f"user:{user_id}", "member", "team")
        # 개인 문서: PG user_doc_grants 테이블 (listObjects 사용 시 전체 문서 반환으로 2-tier 전략 파괴됨)
        personal_docs = self._query_personal_docs(user_id)
        return UserPermission(user_id=user_id, teams=teams, personal_docs=personal_docs)

    def _query_personal_docs(self, user_id: str) -> list[str]:
        """user_doc_grants PG 테이블에서 개인 허용 문서 조회. pg_dsn 미설정 시 빈 목록."""
        if not self._config.pg_dsn:
            return []
        import psycopg2
        try:
            with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT doc_id FROM user_doc_grants WHERE user_id = %s", (user_id,)
                )
                return [row[0] for row in cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            return []

    def _list_fga_objects(self, user: str, relation: str, type_: str) -> list[str]:
        """OpenFGA listObjects 호출. 테스트에서 patch 대상."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.models import ClientListObjectsRequest

        async def _inner():
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            if self._config.api_key:
                from openfga_sdk.credentials import CredentialConfiguration, CredentialMethod
                cfg.credentials = CredentialConfiguration(
                    method=CredentialMethod.API_TOKEN,
                    configuration=CredentialConfiguration(api_token=self._config.api_key),
                )
            async with OpenFgaClient(cfg) as client:
                resp = await client.list_objects(
                    ClientListObjectsRequest(user=user, relation=relation, type=type_)
                )
                return resp.objects or []

        return asyncio.run(_inner())

    def _write_fga_tuples(self, tuples: list[dict]) -> None:
        """OpenFGA write 호출. 테스트에서 patch 대상."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.models import ClientWriteRequest, TupleKey

        async def _inner():
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            async with OpenFgaClient(cfg) as client:
                await client.write(ClientWriteRequest(
                    writes=[TupleKey(**t) for t in tuples]
                ))

        asyncio.run(_inner())

    def write_tuples(
        self, doc_id: str, owner_id: str, team_id: str, sensitivity: str
    ) -> None:
        tuples = [{"user": f"user:{owner_id}", "relation": "owner", "object": f"document:{doc_id}"}]
        if sensitivity == "public":
            tuples.append({"user": "user:*", "relation": "viewer", "object": f"document:{doc_id}"})
        elif sensitivity == "internal":
            tuples.append({"user": f"{team_id}#member", "relation": "viewer", "object": f"document:{doc_id}"})
        elif sensitivity == "secret":
            # secret 문서는 개별 지정만 — owner만 viewer로 등록 후 pg_doc_grants에도 기록
            tuples.append({"user": f"user:{owner_id}", "relation": "viewer", "object": f"document:{doc_id}"})
            self._insert_personal_doc(owner_id, doc_id)
        self._write_fga_tuples(tuples)
        self._cache.invalidate(owner_id)

    def _insert_personal_doc(self, user_id: str, doc_id: str) -> None:
        if not self._config.pg_dsn:
            return
        import psycopg2
        with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_doc_grants (
                    user_id TEXT NOT NULL,
                    doc_id  TEXT NOT NULL,
                    PRIMARY KEY (user_id, doc_id)
                )
            """)
            cur.execute(
                "INSERT INTO user_doc_grants (user_id, doc_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, doc_id),
            )

    def _delete_personal_doc(self, user_id: str, doc_id: str) -> None:
        if not self._config.pg_dsn:
            return
        import psycopg2
        with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_doc_grants WHERE user_id = %s AND doc_id = %s",
                (user_id, doc_id),
            )

    def add_team_member(self, user_id: str, team_id: str) -> None:
        self._write_fga_tuples([{"user": f"user:{user_id}", "relation": "member", "object": f"team:{team_id}"}])
        self._cache.invalidate(user_id)

    def remove_team_member(self, user_id: str, team_id: str) -> None:
        async def _inner():
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            from openfga_sdk.models import ClientWriteRequest, TupleKey
            cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
            async with OpenFgaClient(cfg) as client:
                await client.write(ClientWriteRequest(
                    deletes=[TupleKey(user=f"user:{user_id}", relation="member", object=f"team:{team_id}")]
                ))
        asyncio.run(_inner())
        self._cache.invalidate(user_id)

    def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        self._write_fga_tuples([{"user": f"user:{user_id}", "relation": "viewer", "object": f"document:{doc_id}"}])
        self._insert_personal_doc(user_id, doc_id)
        self._cache.invalidate(user_id)

    def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        from openfga_sdk.models import ClientWriteRequest, TupleKey

        async def _inner():
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            async with OpenFgaClient(cfg) as client:
                await client.write(ClientWriteRequest(
                    deletes=[TupleKey(user=f"user:{user_id}", relation="viewer", object=f"document:{doc_id}")]
                ))

            asyncio.run(_inner())
        self._delete_personal_doc(user_id, doc_id)
        self._cache.invalidate(user_id)

    def delete_user_tuples(self, user_id: str) -> None:
        """퇴사 처리 — 해당 유저의 모든 tuple 삭제. 캐시 무효화."""
        # OpenFGA에는 "delete all by user" API가 없으므로
        # list_objects로 조회 후 개별 삭제한다.
        docs = self._list_fga_objects(f"user:{user_id}", "can_view", "document")
        teams = self._list_fga_objects(f"user:{user_id}", "member", "team")
        tuples_to_delete = (
            [{"user": f"user:{user_id}", "relation": "viewer", "object": d} for d in docs]
            + [{"user": f"user:{user_id}", "relation": "member", "object": t} for t in teams]
        )
        if tuples_to_delete:
            async def _inner():
                from openfga_sdk import OpenFgaClient, ClientConfiguration
                from openfga_sdk.models import ClientWriteRequest, TupleKey
                cfg = ClientConfiguration(
                    api_url=self._config.api_url,
                    store_id=self._config.store_id,
                )
                async with OpenFgaClient(cfg) as client:
                    await client.write(ClientWriteRequest(
                        deletes=[TupleKey(**t) for t in tuples_to_delete]
                    ))
            asyncio.run(_inner())
        self._cache.invalidate(user_id)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_client.py -v
```
Expected: 전체 PASS (7개)

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/client.py tests/shared/fga/test_client.py
git commit -m "feat(fga): FGAClient.get_permission() + write_tuples() + 캐시 연동 구현"
```

---

## Task 7: `shared/fga/cache/postgres.py` — PostgresCacheBackend

**Files:**
- Create: `shared/fga/cache/postgres.py`
- Create: `tests/shared/fga/test_postgres_cache.py`

> `POSTGRES_DSN` 환경 변수가 필요한 통합 테스트. CI에서 PG가 없으면 skip한다.

- [ ] **Step 1: 테스트 작성**

`tests/shared/fga/test_postgres_cache.py`를 작성한다.

```python
import os
import pytest
from shared.fga.cache.postgres import PostgresCacheBackend
from shared.fga.models import UserPermission


@pytest.fixture
def pg_cache():
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set")
    cache = PostgresCacheBackend(dsn=dsn)
    cache._ensure_table()
    cache.invalidate("test_u1")  # 이전 테스트 잔류 정리
    yield cache
    cache.invalidate("test_u1")


def test_pg_set_and_get(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=["team:dev"], personal_docs=["doc:x"])
    pg_cache.set("test_u1", perm, ttl_seconds=60)
    result = pg_cache.get("test_u1")
    assert result is not None
    assert result.teams == ["team:dev"]
    assert result.personal_docs == ["doc:x"]


def test_pg_expired_returns_none(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=[], personal_docs=[])
    pg_cache.set("test_u1", perm, ttl_seconds=-1)  # 이미 만료
    assert pg_cache.get("test_u1") is None


def test_pg_invalidate(pg_cache):
    perm = UserPermission(user_id="test_u1", teams=["team:ops"], personal_docs=[])
    pg_cache.set("test_u1", perm, ttl_seconds=60)
    pg_cache.invalidate("test_u1")
    assert pg_cache.get("test_u1") is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_postgres_cache.py -v
```
Expected: `ModuleNotFoundError` 또는 skip (POSTGRES_DSN 미설정 시)

- [ ] **Step 3: `shared/fga/cache/postgres.py` 작성**

```python
import json
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class PostgresCacheBackend(PermissionCacheBackend):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conn(self):
        return psycopg2.connect(self._dsn)

    def _ensure_table(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fga_permission_cache (
                    user_id       TEXT PRIMARY KEY,
                    teams         JSONB        NOT NULL DEFAULT '[]',
                    personal_docs JSONB        NOT NULL DEFAULT '[]',
                    expires_at    TIMESTAMPTZ  NOT NULL,
                    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_fga_cache_expires
                ON fga_permission_cache(expires_at)
            """)

    def get(self, user_id: str) -> UserPermission | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT teams, personal_docs FROM fga_permission_cache "
                "WHERE user_id = %s AND expires_at > now()",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return UserPermission(
                user_id=user_id,
                teams=row["teams"],
                personal_docs=row["personal_docs"],
            )

    def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO fga_permission_cache (user_id, teams, personal_docs, expires_at, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    teams = EXCLUDED.teams,
                    personal_docs = EXCLUDED.personal_docs,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
            """, (user_id, json.dumps(perm.teams), json.dumps(perm.personal_docs), expires_at))

    def invalidate(self, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fga_permission_cache WHERE user_id = %s", (user_id,))
```

- [ ] **Step 4: import 확인 (PG 없어도 됨)**

```bash
python -c "from shared.fga.cache.postgres import PostgresCacheBackend; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/cache/postgres.py tests/shared/fga/test_postgres_cache.py
git commit -m "feat(fga): PostgresCacheBackend — TTL 캐시 PG 구현"
```

---

## Task 8: VectorStore/Retriever 인터페이스 변경 — `filter_doc_ids` → `where_filter`

**Files:**
- Modify: `shared/vector_store/base.py`
- Modify: `shared/vector_store/chroma_store.py`
- Modify: `shared/retriever/base.py`
- Modify: `shared/retriever/basic_retriever.py`
- Modify: `tests/shared/test_vector_store.py`
- Modify: `tests/shared/test_retriever.py`

- [ ] **Step 1: `shared/vector_store/base.py` 수정**

`filter_doc_ids` 파라미터를 `where_filter`로 교체한다.

```python
from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_filter: dict | None = None,
    ) -> list[SearchResult]: ...

    @abstractmethod
    def count(self) -> int: ...
```

- [ ] **Step 2: `shared/vector_store/chroma_store.py` 수정**

`search()` 메서드를 아래로 교체한다. `add()`에는 metadata 파라미터를 추가한다.

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

    def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None:
        metadatas = []
        for i, c in enumerate(chunks):
            meta = {"source": c.source}
            if extra_metadata and i < len(extra_metadata):
                meta.update(extra_metadata[i])
            metadatas.append(meta)
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_filter: dict | None = None,
    ) -> list[SearchResult]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self._collection.count(), 1)),
            where=where_filter,
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

- [ ] **Step 4: `shared/retriever/base.py` 수정**

```python
from abc import ABC, abstractmethod
from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 5, where_filter: dict | None = None
    ) -> list[SearchResult]: ...
```

- [ ] **Step 5: `shared/retriever/basic_retriever.py` 수정**

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
        self, query: str, top_k: int = 5, where_filter: dict | None = None
    ) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k, where_filter=where_filter)
```

- [ ] **Step 6: 기존 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py tests/shared/test_retriever.py tests/app/graph/nodes/test_retrieve.py -v 2>&1 | grep -E "FAILED|ERROR" | head -20
```
Expected: `filter_doc_ids` 관련 테스트들 FAIL

- [ ] **Step 7: `tests/shared/test_vector_store.py` 업데이트**

파일에서 `filter_doc_ids` 사용 부분을 `where_filter`로 교체한다.

```bash
grep -n "filter_doc_ids" tests/shared/test_vector_store.py
```

검색 결과의 각 줄에서 `filter_doc_ids=["..."]` → `where_filter={"source": {"$in": ["..."]}}` 로 변경한다.

- [ ] **Step 8: `tests/shared/test_retriever.py` 업데이트**

```bash
grep -n "filter_doc_ids" tests/shared/test_retriever.py
```

검색 결과의 각 줄에서 `filter_doc_ids` → `where_filter` 로 변경한다.

- [ ] **Step 9: 테스트 통과 확인**

```bash
pytest tests/shared/test_vector_store.py tests/shared/test_retriever.py -v
```
Expected: 전체 PASS

- [ ] **Step 10: 커밋**

```bash
git add shared/vector_store/ shared/retriever/ tests/shared/test_vector_store.py tests/shared/test_retriever.py
git commit -m "refactor: VectorStore/Retriever filter_doc_ids → where_filter"
```

---

## Task 9: `AgentState` 확장 + `permission_node` 신규 생성

**Files:**
- Modify: `app/graph/state.py`
- Create: `app/graph/nodes/permission.py`
- Create: `tests/app/graph/nodes/test_permission_node.py`

- [ ] **Step 1: `app/graph/state.py` 수정**

`user_teams`와 `personal_doc_ids`를 추가한다.

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
    user_id: str
    allowed_doc_ids: list[str]   # deprecated — FGA 미연동 테스트 stub용
    user_teams: list[str]        # permission_node가 채움
    personal_doc_ids: list[str]  # permission_node가 채움
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/app/graph/nodes/test_permission_node.py`를 작성한다.

```python
from unittest.mock import MagicMock
from shared.fga.models import UserPermission
from app.graph.nodes.permission import permission_node


def _mock_fga_client(teams=None, personal_docs=None):
    client = MagicMock()
    client.get_permission.return_value = UserPermission(
        user_id="u1",
        teams=teams or ["team:dev"],
        personal_docs=personal_docs or [],
    )
    return client


def test_permission_node_populates_state():
    state = {"user_id": "u1"}
    fga_client = _mock_fga_client(teams=["team:dev"], personal_docs=["doc:secret"])

    result = permission_node(state, fga_client=fga_client)

    assert result["user_teams"] == ["team:dev"]
    assert result["personal_doc_ids"] == ["doc:secret"]
    fga_client.get_permission.assert_called_once_with("u1")


def test_permission_node_empty_when_no_permissions():
    state = {"user_id": "u2"}
    fga_client = _mock_fga_client(teams=[], personal_docs=[])

    result = permission_node(state, fga_client=fga_client)

    assert result["user_teams"] == []
    assert result["personal_doc_ids"] == []
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_permission_node.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 4: `app/graph/nodes/permission.py` 작성**

```python
from shared.fga.client import FGAClient


def permission_node(state: dict, *, fga_client: FGAClient) -> dict:
    perm = fga_client.get_permission(state["user_id"])
    return {
        "user_teams": perm.teams,
        "personal_doc_ids": perm.personal_docs,
    }
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_permission_node.py -v
```
Expected: 2개 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/state.py app/graph/nodes/permission.py tests/app/graph/nodes/test_permission_node.py
git commit -m "feat(graph): AgentState user_teams/personal_doc_ids 추가 + permission_node 구현"
```

---

## Task 10: `retrieve_node` — FGAClient 기반 where_filter 적용

**Files:**
- Modify: `app/graph/nodes/retrieve.py`
- Modify: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: `tests/app/graph/nodes/test_retrieve.py` 업데이트**

기존 파일 전체를 아래로 교체한다.

```python
from unittest.mock import MagicMock
from shared.fga.models import UserPermission
from shared.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text="내용", source="doc.md") -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test-1"), score=0.9)


def _mock_fga(teams=None, personal_docs=None):
    client = MagicMock()
    perm = UserPermission(user_id="u1", teams=teams or [], personal_docs=personal_docs or [])
    client.build_chroma_filter.return_value = {"sensitivity": "public"} if not teams else {
        "$or": [{"sensitivity": "public"}, {"$and": [{"team_id": {"$in": teams}}, {"sensitivity": "internal"}]}]
    }
    return client


def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result()]
    mock_fga = _mock_fga()

    state = {"question": "테스트 질문", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}
    result = retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert "documents" in result
    assert len(result["documents"]) == 1


def test_retrieve_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga()

    retrieve_node(
        {"question": "원본", "rewritten_question": "재작성", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    call_args = mock_retriever.retrieve.call_args
    assert call_args[0][0] == "재작성"


def test_retrieve_node_passes_where_filter():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga(teams=["team:dev"])
    mock_fga.build_chroma_filter.return_value = {"expected": "filter"}

    retrieve_node(
        {"question": "q", "user_id": "u1", "user_teams": ["team:dev"], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    _, kwargs = mock_retriever.retrieve.call_args
    assert kwargs["where_filter"] == {"expected": "filter"}


def test_retrieve_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga()

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": "", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    call_args = mock_retriever.retrieve.call_args
    assert call_args[0][0] == "원본 질문"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: `TypeError` (retrieve_node 시그니처 불일치)

- [ ] **Step 3: `app/graph/nodes/retrieve.py` 교체**

```python
from shared.fga.client import FGAClient
from shared.fga.models import UserPermission
from shared.models import SearchResult
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker
from shared.retriever.base import Retriever


def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    fga_client: FGAClient,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    query = state.get("rewritten_question") or state["question"]
    perm = UserPermission(
        user_id=state.get("user_id", "anonymous"),
        teams=state.get("user_teams", []),
        personal_docs=state.get("personal_doc_ids", []),
    )
    where_filter = fga_client.build_chroma_filter(perm)
    results: list[SearchResult] = retriever.retrieve(
        query, top_k=retrieve_top_k, where_filter=where_filter
    )
    _reranker = reranker or NoOpReranker()
    reranked = _reranker.rerank(query, results, top_k=top_k)
    return {"documents": reranked}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: 4개 PASS

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/retrieve.py tests/app/graph/nodes/test_retrieve.py
git commit -m "feat(graph): retrieve_node FGAClient where_filter 적용"
```

---

## Task 11: `app/graph/builder.py` — permission_node 연결

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: `app/graph/builder.py` 수정**

`build_graph()`에 `fga_client` 파라미터를 추가하고, `permission_node`를 `doc_search` 경로에 삽입한다.

```python
import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.llm.base import LLMClient
from shared.models import Answer
from shared.reranker.base import Reranker
from shared.retriever.base import Retriever
from app.graph.edges import (
    route_after_confirm,
    route_after_grade,
    route_after_hallucination,
    route_after_router,
)
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.confirm import confirm_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.load_memory import load_memory_node
from app.graph.nodes.permission import permission_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node
from app.graph.nodes.save_memory import save_memory_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
from app.graph.state import AgentState


def _default_fga_client() -> FGAClient:
    """FGA 미설정 환경(테스트/로컬)용 — 모든 문서를 public으로 취급."""
    config = FGAConfig(api_url="http://localhost:8080", store_id="")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
    reranker: Reranker | None = None,
    fga_client: FGAClient | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> CompiledStateGraph:
    _fga = fga_client or _default_fga_client()
    g = StateGraph(AgentState)

    g.add_node("load_memory", load_memory_node)
    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("router", partial(router_node, llm=llm))
    g.add_node("permission", partial(permission_node, fga_client=_fga))
    g.add_node("retrieve", partial(
        retrieve_node,
        retriever=retriever,
        fga_client=_fga,
        reranker=reranker,
        retrieve_top_k=retrieve_top_k,
        top_k=top_k,
    ))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("web_search", partial(web_search_node, retriever=web_search_retriever))
    g.add_node("confirm", confirm_node)
    g.add_node("tool_executor", tool_executor_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))
    g.add_node("save_memory", save_memory_node)

    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "rewrite_query")
    g.add_edge("rewrite_query", "router")

    g.add_conditional_edges(
        "router",
        route_after_router,
        {"doc_search": "permission", "web_search": "web_search", "tool_call": "confirm"},
    )

    # doc_search: permission → retrieve → grade
    g.add_edge("permission", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    g.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {"tool_executor": "tool_executor", "end": END},
    )
    g.add_edge("tool_executor", "generate")
    g.add_edge("web_search", "generate")

    g.add_edge("generate", "check_hallucination")
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"save_memory": "save_memory", "generate": "generate"},
    )
    g.add_edge("save_memory", END)

    return g.compile(checkpointer=MemorySaver())


def _ensure_thread_id(config: dict | None) -> dict:
    if config is None:
        return {"configurable": {"thread_id": str(uuid.uuid4())}}
    if "configurable" not in config:
        return {**config, "configurable": {"thread_id": str(uuid.uuid4())}}
    if "thread_id" not in config["configurable"]:
        return {**config, "configurable": {**config["configurable"], "thread_id": str(uuid.uuid4())}}
    return config


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
        "user_teams": [],
        "personal_doc_ids": [],
    }
    final = graph.invoke(initial, config=config)
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 2: 기존 builder 테스트 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```

`build_graph()` 테스트에서 `_default_fga_client()`가 사용되므로 mock 없이도 통과해야 한다. `permission_node`가 FGA 호출을 시도하면 실패하므로, 기존 테스트에서 `get_permission`을 mock해야 한다면 아래를 추가한다.

`tests/app/graph/test_builder.py`의 `build_graph` 호출 전 `_default_fga_client` mock을 추가한다.

```python
from unittest.mock import patch, MagicMock
from shared.fga.models import UserPermission

# 기존 테스트 함수들에 아래 패치 데코레이터를 추가한다.
# 예시:
@patch("app.graph.builder._default_fga_client")
def test_build_graph_returns_compiled_graph(mock_fga_factory):
    mock_fga = MagicMock()
    mock_fga.get_permission.return_value = UserPermission(user_id="u", teams=[], personal_docs=[])
    mock_fga.build_chroma_filter.return_value = {"sensitivity": "public"}
    mock_fga_factory.return_value = mock_fga
    # ... 기존 테스트 내용 유지 ...
```

`tests/app/graph/test_builder.py` 전체에서 `build_graph` 호출이 있는 테스트 함수마다 위 패치 데코레이터를 적용한다.

- [ ] **Step 3: 테스트 통과 확인**

```bash
pytest tests/app/graph/test_builder.py -v
```
Expected: 전체 PASS

- [ ] **Step 4: 커밋**

```bash
git add app/graph/builder.py app/graph/nodes/permission.py tests/app/graph/test_builder.py
git commit -m "feat(graph): builder에 permission_node 연결, fga_client 파라미터 추가"
```

---

## Task 12: `shared/indexer/indexer.py` + `app/ingestion/indexer.py` — FGA 문서 등록

**Files:**
- Modify: `shared/indexer/indexer.py`
- Modify: `app/ingestion/indexer.py`
- Modify: `tests/shared/test_indexer.py`

- [ ] **Step 1: `shared/indexer/indexer.py` 수정**

`FGAClient` DI 추가, `add()` 시 `extra_metadata` 전달.

```python
from shared.chunker.base import Chunker
from shared.embedder.base import Embedder
from shared.fga.sensitivity import detect_sensitivity
from shared.loader.base import DocumentLoader
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        fga_client=None,   # FGAClient | None — 순환 import 방지로 타입 미지정
        default_team_id: str = "team:general",
        default_owner_id: str = "user:system",
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._fga_client = fga_client
        self._default_team_id = default_team_id
        self._default_owner_id = default_owner_id

    def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])

        doc_metadata: dict[str, dict] = {}
        for c in chunks:
            if c.source not in doc_metadata:
                full_text = " ".join(ch.text for ch in chunks if ch.source == c.source)
                sensitivity = detect_sensitivity(full_text)
                doc_metadata[c.source] = {
                    "document_id": f"doc:{c.source}",
                    "team_id": self._default_team_id,
                    "sensitivity": sensitivity,
                }

        extra_metadata = [doc_metadata[c.source] for c in chunks]
        self._store.add(chunks, embeddings, extra_metadata=extra_metadata)

        if self._fga_client:
            for source, meta in doc_metadata.items():
                self._fga_client.write_tuples(
                    doc_id=meta["document_id"],
                    owner_id=self._default_owner_id,
                    team_id=meta["team_id"],
                    sensitivity=meta["sensitivity"],
                )
        return len(chunks)
```

- [ ] **Step 2: `tests/shared/test_indexer.py` 업데이트**

기존 테스트에서 `store.add`의 `extra_metadata` 파라미터가 추가됐으므로 mock assertion을 수정한다.

```bash
grep -n "store.add\|mock.*add" tests/shared/test_indexer.py
```

`store.add.assert_called_once_with(chunks, embeddings)` → `store.add.assert_called_once_with(chunks, embeddings, extra_metadata=mock.ANY)` 로 변경.

- [ ] **Step 3: `app/ingestion/indexer.py` 수정**

```python
from shared.config import load_config
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


def build_index(docs_path: str) -> None:
    config = load_config()
    loader = MarkdownLoader()
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)
    store = create_vector_store(config)

    fga_client = None
    if config.fga_store_id:
        fga_config = FGAConfig(
            api_url=config.fga_api_url,
            store_id=config.fga_store_id,
            api_key=config.fga_api_key,
            cache_ttl_seconds=config.fga_cache_ttl_seconds,
        )
        cache = InMemoryCacheBackend()
        fga_client = FGAClient(config=fga_config, cache=cache)

    Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        fga_client=fga_client,
    ).index(docs_path)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_indexer.py tests/app/ingestion/ -v
```
Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/indexer/indexer.py app/ingestion/indexer.py tests/shared/test_indexer.py
git commit -m "feat(indexer): FGA tuple 등록 + metadata(team_id, sensitivity) Chroma 저장"
```

---

## Task 13: `app/api/admin.py` — FGA 관리 엔드포인트

**Files:**
- Modify: `app/api/admin.py`
- Modify: `tests/app/api/test_admin.py`

- [ ] **Step 1: `app/api/admin.py`에 FGA 엔드포인트 추가**

파일 상단 import에 추가하고, 라우터 하단에 아래 엔드포인트를 추가한다.

```python
# 상단 import에 추가
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig


def _get_fga_client() -> FGAClient:
    fga_config = FGAConfig(
        api_url=_config.fga_api_url,
        store_id=_config.fga_store_id,
        api_key=_config.fga_api_key,
        cache_ttl_seconds=_config.fga_cache_ttl_seconds,
    )
    return FGAClient(config=fga_config, cache=InMemoryCacheBackend())


# ── FGA 팀 관리 ────────────────────────────────────────────

@router.post("/users/{user_id}/teams/{team_id}", status_code=204)
def add_user_to_team(
    user_id: str,
    team_id: str,
    _: AuthUser = Depends(require_admin),
) -> None:
    _get_fga_client().add_team_member(user_id, team_id)


@router.delete("/users/{user_id}/teams/{team_id}", status_code=204)
def remove_user_from_team(
    user_id: str,
    team_id: str,
    _: AuthUser = Depends(require_admin),
) -> None:
    _get_fga_client().remove_team_member(user_id, team_id)


@router.delete("/users/{user_id}", status_code=204)
def offboard_user(
    user_id: str,
    _: AuthUser = Depends(require_admin),
) -> None:
    _get_fga_client().delete_user_tuples(user_id)


# ── FGA 문서 개별 공유 ─────────────────────────────────────

@router.post("/documents/{doc_id}/viewers/{user_id}", status_code=204)
def grant_doc_viewer(
    doc_id: str,
    user_id: str,
    _: AuthUser = Depends(require_admin),
) -> None:
    _get_fga_client().grant_doc_access(user_id, f"doc:{doc_id}")


@router.delete("/documents/{doc_id}/viewers/{user_id}", status_code=204)
def revoke_doc_viewer(
    doc_id: str,
    user_id: str,
    _: AuthUser = Depends(require_admin),
) -> None:
    _get_fga_client().revoke_doc_access(user_id, f"doc:{doc_id}")
```

- [ ] **Step 2: 기존 admin 테스트 통과 확인**

```bash
pytest tests/app/api/test_admin.py -v
```
Expected: 기존 테스트 PASS (신규 FGA 엔드포인트는 FGA 서버 없으면 호출 안 됨)

- [ ] **Step 3: 커밋**

```bash
git add app/api/admin.py
git commit -m "feat(api): FGA 팀/문서 관리 Admin API 엔드포인트 추가"
```

---

## Task 14: 통합 테스트

**Files:**
- Create: `tests/app/test_rag_with_fga.py`

- [ ] **Step 1: 통합 테스트 작성**

`tests/app/test_rag_with_fga.py`를 작성한다.

```python
"""
FGA 권한별 Chroma 검색 통합 테스트.
실제 Chroma (임베디드) + InMemoryCacheBackend + FGA API mock 사용.
"""
from unittest.mock import MagicMock, patch
import pytest

from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.models import Chunk, SearchResult


def _make_fga_client(teams=None, personal_docs=None) -> FGAClient:
    config = FGAConfig(api_url="http://localhost", store_id="test")
    client = FGAClient(config=config, cache=InMemoryCacheBackend())
    perm = UserPermission(user_id="u1", teams=teams or [], personal_docs=personal_docs or [])
    client._cache.set("u1", perm, ttl_seconds=60)
    return client


def _mock_retriever(chunks: list[tuple[str, str, str]]) -> MagicMock:
    """chunks: [(text, source, sensitivity)]"""
    mock = MagicMock()
    def fake_retrieve(query, top_k=5, where_filter=None):
        results = []
        for text, source, sensitivity in chunks:
            meta = {"sensitivity": sensitivity, "source": source}
            if where_filter is None:
                results.append(SearchResult(
                    chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
                ))
            else:
                # 간단한 where_filter 시뮬레이션
                if _matches_filter(meta, where_filter):
                    results.append(SearchResult(
                        chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
                    ))
        return results[:top_k]
    mock.retrieve.side_effect = fake_retrieve
    return mock


def _matches_filter(meta: dict, f: dict) -> bool:
    if "$or" in f:
        return any(_matches_filter(meta, c) for c in f["$or"])
    if "$and" in f:
        return all(_matches_filter(meta, c) for c in f["$and"])
    for key, cond in f.items():
        if isinstance(cond, dict) and "$in" in cond:
            if meta.get(key) not in cond["$in"]:
                return False
        else:
            if meta.get(key) != cond:
                return False
    return True


def test_public_doc_accessible_to_all():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([("공개 내용", "public.md", "public")])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "공개 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "public.md"


def test_internal_doc_blocked_without_team():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([("내부 내용", "internal.md", "internal")])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "내부 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0


def test_internal_doc_accessible_with_correct_team():
    fga = _make_fga_client(teams=["team:dev"], personal_docs=[])
    retriever = _mock_retriever([
        ("팀 내부", "internal.md", "internal"),
        ("공개", "public.md", "public"),
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "팀 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    # 캐시에 team:dev 있으므로 user_teams = ["team:dev"]
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    sources = [r.chunk.source for r in result["documents"]]
    assert "internal.md" in sources
    assert "public.md" in sources


def test_secret_doc_accessible_only_with_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=["doc:salary.md"])
    retriever = _mock_retriever([("급여 내역", "salary.md", "secret")])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "salary.md"


def test_secret_doc_blocked_without_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([("급여 내역", "salary.md", "secret")])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0
```

- [ ] **Step 2: 테스트 실행**

```bash
pytest tests/app/test_rag_with_fga.py -v
```
Expected: 5개 PASS

- [ ] **Step 3: 전체 테스트 suite 실행**

```bash
pytest --tb=short -q
```
Expected: 전체 PASS (실패 없음)

- [ ] **Step 4: 커밋**

```bash
git add tests/app/test_rag_with_fga.py
git commit -m "test: FGA 권한별 RAG 통합 테스트 추가"
```

---

## Task 15: ADR 업데이트 + CLAUDE.md 갱신

**Files:**
- Create: `docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md`
- Modify: `plan/access-control.md` (결정 사항 섹션 업데이트)
- Modify: `CLAUDE.md` (ADR 테이블)

- [ ] **Step 1: ADR 파일 생성**

`docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md`를 작성한다.

```markdown
# Decision: listObjects 캐싱 전략 — Redis → PostgreSQL 변경

**Date**: 2026-05-25
**Context**: 기존 ADR(2026-05-23)에서 Redis Cloud를 우선 검토하기로 했으나, 기존 PostgreSQL 재사용으로 변경

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| Redis Cloud | 관리형, 빠르지만 신규 서비스 추가 필요 |
| PostgreSQL (기존 세션 DB) | 인프라 추가 없음, Redis보다 약간 느리지만 충분 |

## Decision

**선택: PostgreSQL — 기존 POSTGRES_DSN 재사용**

## Rationale

세션 스토어로 이미 PostgreSQL을 사용 중이므로 인프라를 추가하지 않는다.
캐시 크기가 작고(유저 수 = row 수) TTL이 60초로 짧아 성능 차이가 무시 가능하다.
`PermissionCacheBackend` ABC로 추후 Redis 교체가 가능하다.
```

- [ ] **Step 2: `CLAUDE.md` ADR 테이블 업데이트**

`CLAUDE.md`의 `## 아키텍처 결정 (ADR)` 테이블에 아래 두 행을 추가한다.

```markdown
| FGA Pre-filter | 2-tier: team_id+sensitivity 메타데이터 필터 + personal_doc_ids. listObjects 전체 목록 미사용 | `docs/superpowers/specs/2026-05-25-access-control-design.md` |
| FGA 캐시 | PostgreSQL TTL 캐시 (Redis 미사용 — 기존 PG 재사용) | `docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md` |
```

- [ ] **Step 3: `plan/access-control.md` 결정 사항 업데이트**

섹션 7의 캐싱 행을 수정한다.

```markdown
| `listObjects` 캐싱 | PostgreSQL TTL 캐시 (기존 POSTGRES_DSN 재사용, Redis 미도입) | [2026-05-25-fga-cache-postgresql.md](../docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md) |
```

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md CLAUDE.md plan/access-control.md
git commit -m "docs(adr): FGA 캐시 전략 Redis → PostgreSQL 변경 기록"
```

---

## Task 16: 회귀 테스트 확인

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest --tb=short -q
```
Expected: 전체 PASS

- [ ] **Step 2: eval 회귀 점수 확인**

```bash
python tests/eval/runner.py
```
Expected: 이전 Phase recall@5 이상 유지. 점수 하락 시 원인 명시 후 fix.

- [ ] **Step 3: 최종 커밋 (필요 시)**

회귀 수정이 있으면 커밋 후 태그 생성은 PR merge 후 진행한다.
