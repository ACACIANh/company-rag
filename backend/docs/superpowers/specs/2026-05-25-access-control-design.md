# 접근 권한 제어 설계 스펙

**Date**: 2026-05-25
**Approach**: ABC 패턴 캐시 — `shared/fga/` 모듈, 2-tier Pre-filter, PostgreSQL TTL 캐시

---

## 1. 배경 및 결정 사항

| 항목 | 결정 |
|---|---|
| Authorization 엔진 | OpenFGA (Zanzibar 기반) |
| 캐시 백엔드 | PostgreSQL (기존 세션 DB 재사용) — Redis 미도입 |
| 캐시 무효화 | TTL 기반 (기본 60초) |
| Pre-filter 전략 | 2-tier: `team_id + sensitivity` 메타데이터 필터 + `personal_doc_ids` |
| OpenFGA 호스팅 | 로컬 개발: Docker / 운영: Auth0 FGA |
| 캐시 백엔드 교체 | `PermissionCacheBackend(ABC)` — `InMemoryCacheBackend`(개발) ↔ `PostgresCacheBackend`(운영) |

### `listObjects(전체 doc_id)` 미사용 이유

사용자가 수천 개 문서에 접근 가능한 경우 Chroma `$in` 필터 리스트가 비대해져 성능 저하.
대신 팀 소속(1~5개) + 개인 허용 secret 문서(소규모)만 캐시.

---

## 2. 전체 아키텍처 & 데이터 흐름

```
[JWT 요청] → app/api/deps.py (user_id 추출)
                │
                ▼
         AgentState.user_id
                │
                ▼ (doc_search 경로만)
      permission_node
          │
          └── FGAClient.get_permission(user_id)
                  ├── PostgresCacheBackend.get(user_id)  → Hit: return cached
                  └── Miss/Expired:
                          ├── listObjects(user, member, team)       → user_teams
                          ├── listObjects(user, can_view, document) → personal_doc_ids (secret만)
                          └── PostgresCacheBackend.set(user_id, perm, ttl=60s)
                │
                ▼
         AgentState.user_teams, personal_doc_ids
                │
                ▼
      retrieve_node
          │
          ├── FGAClient.build_chroma_filter(perm)  ← 순수 함수
          └── retriever.retrieve(query, filter=chroma_filter)

[문서 등록] → app/ingestion/indexer.py
          ├── VectorStore.add(chunks, metadata={team_id, sensitivity, ...})
          └── FGAClient.write_tuples(doc_id, owner_id, team_id, sensitivity)
                  └── cache.invalidate(user_id)
```

### 그래프 경로

```
router → permission_node → retrieve_node → grade_documents → ...  (doc_search)
router →                   web_search_node → ...                   (web_search)
router →                   confirm_node → tool_executor → ...      (tool_call)
```

`permission_node`는 `doc_search` 경로에만 삽입. 다른 경로는 영향 없음.

---

## 3. Pre-filter 전략 (2-tier)

### Chroma `where` 절 구성

```python
{
    "$or": [
        {"sensitivity": "public"},                        # 1) 전체 공개 문서
        {
            "$and": [
                {"team_id": {"$in": user_teams}},         # 2) 팀 내부 문서
                {"sensitivity": "internal"}
            ]
        },
        {
            "$and": [
                {"sensitivity": "secret"},
                {"document_id": {"$in": personal_doc_ids}}  # 3) 개인/인사 문서
            ]
        }
    ]
}
```

`user_teams`와 `personal_doc_ids`가 모두 비어 있으면 → `public` 문서만 반환.

### OpenFGA 호출 분리

| 목적 | FGA 호출 | 예상 크기 |
|---|---|---|
| 팀 소속 | `listObjects(user:{id}, member, team)` | 1~5개 |
| 개인 secret 문서 | `listObjects(user:{id}, can_view, document)` → Python에서 secret만 필터 | 소규모 |

---

## 4. `shared/fga/` 모듈 구조

```
shared/fga/
├── __init__.py
├── base.py              # PermissionCacheBackend(ABC)
├── client.py            # FGAClient — openfga-sdk 래퍼 + build_chroma_filter()
├── models.py            # UserPermission dataclass, FGAConfig dataclass
├── sensitivity.py       # detect_sensitivity(text) → "public"|"internal"|"secret"
└── cache/
    ├── __init__.py
    ├── postgres.py      # PostgresCacheBackend
    └── memory.py        # InMemoryCacheBackend (개발/테스트용)
```

### `base.py`

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

### `models.py`

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
    api_key: str          # Auth0 FGA용, 로컬 Docker는 ""
    cache_ttl_seconds: int = 60
```

### `client.py` 핵심 인터페이스

```python
class FGAClient:
    def __init__(self, config: FGAConfig, cache: PermissionCacheBackend): ...

    def get_permission(self, user_id: str) -> UserPermission:
        # 1) cache hit → return
        # 2) miss → FGA listObjects × 2 → cache.set → return

    def write_tuples(self, doc_id: str, owner_id: str, team_id: str, sensitivity: str) -> None:
        # OpenFGA write + cache.invalidate(owner_id)

    def delete_user_tuples(self, user_id: str) -> None:
        # 퇴사 처리 — 모든 tuple 삭제 + cache.invalidate(user_id)

    def build_chroma_filter(self, perm: UserPermission) -> dict:
        # 순수 함수 — 2-tier $or 필터 dict 반환
```

### `sensitivity.py`

```python
def detect_sensitivity(text: str) -> str:
    text = text.lower()
    if any(k in text for k in ["기밀", "급여", "인사", "연봉", "평가"]):
        return "secret"
    if any(k in text for k in ["내부", "draft", "internal"]):
        return "internal"
    return "public"
```

---

## 5. PostgreSQL 스키마

```sql
CREATE TABLE fga_permission_cache (
    user_id       TEXT PRIMARY KEY,
    teams         JSONB        NOT NULL DEFAULT '[]',
    personal_docs JSONB        NOT NULL DEFAULT '[]',
    expires_at    TIMESTAMPTZ  NOT NULL,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_fga_cache_expires ON fga_permission_cache(expires_at);
```

- 만료 행 정리: 조회 시 `WHERE expires_at > now()` 조건 적용 (별도 크론 불필요)
- 기존 `POSTGRES_DSN` 재사용 — 신규 서비스 추가 없음

---

## 6. Config 변경 (`shared/config.py`)

```python
@dataclass
class Config:
    ...기존 필드...

    # OpenFGA
    fga_api_url:           str  # "http://localhost:8080" | Auth0 FGA URL
    fga_store_id:          str
    fga_api_key:           str  # 로컬 Docker는 ""

    # Permission cache
    fga_cache_backend:     str  # "postgres" | "memory"
    fga_cache_ttl_seconds: int  # 기본값 60
```

```bash
# 로컬 개발
FGA_API_URL=http://localhost:8080
FGA_STORE_ID=01HXY...
FGA_API_KEY=
FGA_CACHE_BACKEND=memory

# 운영
FGA_API_URL=https://api.us1.fga.dev
FGA_STORE_ID=01HXY...
FGA_API_KEY=fga_sk_...
FGA_CACHE_BACKEND=postgres
FGA_CACHE_TTL_SECONDS=60
```

---

## 7. AgentState 변경

```python
class AgentState(TypedDict):
    ...기존 필드...
    user_id: str                    # 이미 존재 ✓
    allowed_doc_ids: list[str]      # deprecated — FGA 없는 테스트 stub용으로만 유지
    user_teams: list[str]           # 추가 — permission_node가 채움
    personal_doc_ids: list[str]     # 추가 — permission_node가 채움
```

---

## 8. 그래프 노드 변경

### `app/graph/nodes/permission.py` (신규)

```python
def permission_node(state: dict, *, fga_client: FGAClient) -> dict:
    perm = fga_client.get_permission(state["user_id"])
    return {"user_teams": perm.teams, "personal_doc_ids": perm.personal_docs}
```

### `app/graph/nodes/retrieve.py` 변경

```python
def retrieve_node(state: dict, *, retriever, fga_client: FGAClient, reranker=None, ...):
    query = state.get("rewritten_question") or state["question"]
    perm = UserPermission(
        user_id=state["user_id"],
        teams=state.get("user_teams", []),
        personal_docs=state.get("personal_doc_ids", []),
    )
    chroma_filter = fga_client.build_chroma_filter(perm)
    results = retriever.retrieve(query, top_k=retrieve_top_k, filter=chroma_filter)
    reranked = (reranker or NoOpReranker()).rerank(query, results, top_k=top_k)
    return {"documents": reranked}
```

---

## 9. 문서 등록 파이프라인

`app/ingestion/indexer.py` 변경:

```python
class Indexer:
    def __init__(self, ..., fga_client: FGAClient | None = None): ...

    def index(self, doc, team_id: str, owner_id: str) -> None:
        sensitivity = detect_sensitivity(doc.text)
        doc_id = f"doc:{doc.source}"

        self._store.add(chunks, embeddings, metadata=[{
            "source":      doc.source,
            "document_id": doc_id,
            "team_id":     team_id,
            "sensitivity": sensitivity,
        }])

        if self.fga_client:
            self.fga_client.write_tuples(doc_id, owner_id, team_id, sensitivity)
```

`fga_client=None`이면 FGA 없이 동작 — 기존 테스트 호환 유지.

---

## 10. Admin API (`app/api/admin.py`)

```
POST   /admin/users/{user_id}/teams/{team_id}           # 입사 / 팀 추가
DELETE /admin/users/{user_id}/teams/{team_id}           # 팀 이탈
DELETE /admin/users/{user_id}                           # 퇴사 (모든 tuple 삭제)
POST   /admin/documents/{doc_id}/viewers/{user_id}      # secret 문서 개별 공유
DELETE /admin/documents/{doc_id}/viewers/{user_id}      # 공유 해제
```

모든 write/delete 후 `fga_client.cache.invalidate(user_id)` 호출.

---

## 11. 테스트 전략

### 단위 테스트

```
tests/shared/fga/
├── test_sensitivity.py       # detect_sensitivity() 키워드 매칭 (pure)
├── test_fga_client.py        # build_chroma_filter() — FGA API mock
├── test_memory_cache.py      # TTL 만료, invalidate 동작
└── test_postgres_cache.py    # DB 픽스처 사용

tests/app/graph/nodes/
├── test_permission_node.py   # FGAClient mock → state 반환 검증
└── test_retrieve_node.py     # user_teams/personal_doc_ids 필드 추가 반영
```

### 핵심 테스트 케이스

| 케이스 | 검증 포인트 |
|---|---|
| public 문서 | 팀 조건 없이 반환 |
| internal 문서 | `team_id IN user_teams` 조건 포함 |
| secret 문서 | `doc_id IN personal_doc_ids` 조건 포함 |
| 캐시 히트 | FGA API 호출 0회 |
| TTL 만료 | 재조회 시 FGA API 1회 호출 |
| 퇴사 처리 | `invalidate()` → 다음 조회 시 FGA 재호출 |
| `fga_client=None` | 기존 `allowed_doc_ids` 경로 그대로 동작 |

### 통합 테스트

```
tests/app/test_rag_with_fga.py
# 실제 Chroma + InMemoryCacheBackend + FGA API mock
# 시나리오: 문서 등록 → 권한별 검색 결과 검증
```

---

## 12. OpenFGA Authorization Model

```
model
  schema 1.1

type user

type team
  relations
    define member : [user]
    define admin  : [user]

type document
  relations
    define owner    : [user]
    define editor   : [user, team#member]
    define viewer   : [user, team#member, editor]
    define can_edit : editor or owner
    define can_view : viewer or can_edit
```

---

## 13. 레이어 경계 준수

- `shared/fga/` — LangGraph import 금지. 순수 Python + openfga-sdk
- `app/graph/nodes/` — `shared/fga/` ABC 인터페이스만 의존
- `app/ingestion/` — `FGAClient` DI, `fga_client=None`이면 FGA 없이 동작
- `app/api/admin.py` — `FGAClient.write_tuples()` / `delete_user_tuples()` 호출

---

## 14. DoD (Definition of Done)

- [ ] `shared/fga/` 단위 테스트 전체 통과
- [ ] `permission_node` 단위 테스트 추가
- [ ] `retrieve_node` 기존 테스트 호환 유지
- [ ] 통합 테스트: 팀/개인/public 문서 권한별 검색 검증
- [ ] `tests/eval/runner.py` 회귀 점수 이전 Phase 이상 유지
- [ ] CLAUDE.md ADR 섹션에 캐시 전략 변경 (Redis → PostgreSQL) 반영
- [ ] ADR 파일 생성: `docs/superpowers/decisions/2026-05-25-fga-cache-postgresql.md`
