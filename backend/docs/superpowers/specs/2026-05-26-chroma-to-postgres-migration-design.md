# Chroma → PostgreSQL(pgvector) 마이그레이션 설계

**날짜**: 2026-05-26  
**상태**: 승인됨  
**범위**: 벡터 스토어 교체 + 전체 DB 드라이버 asyncpg 단일화

---

## 배경

- 벡터 스토어로 Chroma(chromadb)를 사용 중이었으나, 이미 PostgreSQL이 FGA 캐시·세션·user_doc_grants 용도로 가동 중
- 드라이버를 asyncpg로 단일화하고 pgvector 확장을 사용해 벡터 저장소도 PostgreSQL로 통합
- psycopg2-binary, chromadb 의존성 완전 제거

---

## 1. 데이터 스키마

### docker-compose 이미지 교체
```yaml
# 변경 전
image: postgres:16-alpine
# 변경 후
image: pgvector/pgvector:pg16
```

### documents 테이블 (신규)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content     TEXT NOT NULL,
    embedding   vector(1536),
    metadata    JSONB DEFAULT '{}',
    team_id     TEXT,
    sensitivity TEXT DEFAULT 'public',
    owner_id    TEXT,
    doc_id      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON documents (team_id, sensitivity);
```

- 기존 Chroma 메타데이터 필드(`team_id`, `sensitivity`, `owner_id`, `doc_id`)를 SQL 컬럼으로 승격
- FGA 필터를 WHERE 절로 처리하여 Chroma `$and`/`$in` dict 제거
- 임베딩 차원 1536은 `Config`에서 주입 가능하도록 설계

---

## 2. 레이어 구조 변경

### shared/vector_store/
| 파일 | 변경 |
|------|------|
| `chroma_store.py` | **삭제** |
| `postgres_store.py` | **신규** — `PostgresVectorStore(VectorStore)` |
| `factory.py` | `ChromaStore` → `PostgresVectorStore` |
| `base.py` | 인터페이스 유지 (변경 없음) |

### PostgresVectorStore 인터페이스
```python
class PostgresVectorStore(VectorStore):
    async def add_documents(self, docs: list[Document]) -> None: ...
    async def search(
        self,
        query_embedding: list[float],
        where_clause: str = "",
        params: list = [],
        k: int = 5,
    ) -> list[Document]: ...
    async def delete(self, doc_ids: list[str]) -> None: ...
```

`search()` 내부 SQL 예시:
```sql
SELECT content, metadata, team_id, sensitivity, owner_id, doc_id,
       1 - (embedding <=> $1) AS score
FROM documents
WHERE <where_clause>
ORDER BY embedding <=> $1
LIMIT $N;
```

---

## 3. FGA 필터 변경

### shared/fga/client.py
```python
# 변경 전
def build_chroma_filter(self, perm: UserPermission) -> dict: ...

# 변경 후
def build_pg_filter(self, perm: UserPermission) -> tuple[str, list]:
    """Returns (WHERE clause string, params list)"""
```

반환 예시:
```python
# public only
("sensitivity = 'public'", [])

# team member
("team_id = ANY($1) AND sensitivity != 'secret'", [["team-a", "team-b"]])

# personal secret docs
(
  "(team_id = ANY($1) AND sensitivity != 'secret') OR (doc_id = ANY($2))",
  [["team-a"], ["doc-1", "doc-2"]]
)
```

### app/graph/nodes/retrieve.py
```python
# 변경 전
where_filter = fga_client.build_chroma_filter(perm)
docs = vector_store.search(query, where=where_filter)

# 변경 후
where_clause, params = fga_client.build_pg_filter(perm)
docs = await vector_store.search(query_embedding, where_clause, params)
```

---

## 4. asyncpg 전체 전환

### 대상 파일
| 파일 | 변경 내용 |
|------|---------|
| `shared/fga/cache/postgres.py` | `psycopg2.pool.ThreadedConnectionPool` → `asyncpg.Pool` |
| `shared/session/adapters/postgres.py` | `psycopg2.pool.ThreadedConnectionPool` → `asyncpg.Pool` |
| `shared/fga/client.py` | `psycopg2.connect()` 직접 호출 → `asyncpg.Pool` 주입 |
| `app/graph/nodes/retrieve.py` | `def` → `async def` |

### Pool 생성 패턴 (공통)
```python
import asyncpg

async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=2, max_size=10)
```

Pool은 애플리케이션 시작 시 한 번 생성해 의존성 주입으로 전달합니다.

### pgvector 등록 (asyncpg 필수)
```python
from pgvector.asyncpg import register_vector

async def init_pool(conn):
    await register_vector(conn)

pool = await asyncpg.create_pool(dsn, init=init_pool)
```

---

## 5. 설정(Config) 변경

### 제거
```python
# shared/config.py
chroma_mode: str   # CHROMA_MODE
chroma_path: str   # CHROMA_PATH
vector_store: str  # VECTOR_STORE (항상 postgres)
```

### 추가 없음
- `POSTGRES_DSN`은 이미 존재
- `VECTOR_TABLE`은 하드코딩(`"documents"`)으로 충분

---

## 6. 의존성 변경

### requirements.txt
```diff
- chromadb>=0.5.0
- psycopg2-binary>=2.9.0
+ asyncpg>=0.29.0
+ pgvector>=0.3.0
```

---

## 7. 테스트 변경

| 파일 | 변경 |
|------|------|
| `tests/shared/test_vector_store.py` | Chroma 테스트 → PostgresVectorStore (pytest-asyncio + 실DB or mock) |
| `tests/shared/test_config.py` | `chroma_*` 필드 검증 제거 |
| `tests/shared/fga/test_client.py` | `build_chroma_filter` → `build_pg_filter` 반환값 검증 |
| `tests/app/test_rag_with_fga.py` | Chroma 통합 테스트 → pgvector 통합 테스트 |
| `tests/app/graph/test_builder.py` | `mock_fga.build_chroma_filter` → `build_pg_filter` |
| `tests/app/graph/nodes/test_retrieve.py` | `build_chroma_filter` mock → `build_pg_filter` |
| `tests/shared/fga/test_postgres_cache.py` | asyncpg 기반으로 재작성 |
| `tests/shared/test_session_store.py` | asyncpg 기반으로 재작성 |

---

## 8. DoD

1. `chromadb`, `psycopg2-binary` requirements에서 제거
2. `PostgresVectorStore` 단위 테스트 통과
3. `build_pg_filter` 단위 테스트 통과
4. `tests/eval/runner.py` 회귀 점수 확인 (하락 시 원인 명시)
5. docker-compose `pgvector/pgvector:pg16` 이미지로 정상 기동
