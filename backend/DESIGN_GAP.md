# 권한 RAG — 현재 vs 목표 차이 분석 (AI 인계용)

> 목적: DESIGN.md(목표 상태)와 기존 코드의 차이를 AI 에이전트가 바로 작업에 착수할 수 있도록 정리한 문서.
> 기준 커밋: main (7ba9df1)
> ⚠️ DESIGN.md가 25번째 줄("3. vectorstore에서 path prefix")에서 잘려 있음. 이 문서는 "path prefix 매칭으로 필터링 후 벡터 검색"으로 해석함.

---

## 0. 목표 상태 요약 (DESIGN.md)

- **pre-filter 방식**: 권한 통과 폴더를 먼저 받고, 그 범위에서만 벡터 검색
- **개인 단위 메타데이터 없음**. 권한 주체는 **부서 단위**
- **폴더 권한은 트리 상속**
- **인덱싱**: 청크 메타데이터에 `path`를 경로 형태로 저장 (예: `/projects/friday`)
- **OpenFGA 모델**:
  ```
  type user
  type department
    relations
      define member: [user]
  type folder
    relations
      define parent: [folder]
      define viewer: [department#member]
      define can_read: viewer or can_read from parent
  ```
- **검색 흐름**:
  1. OpenFGA `ListObjects`로 사용자가 `can_read` 가능한 folder 목록을 받음
  2. 목록에서 상위 노드만 추림 (부모가 있으면 자식 경로는 버림)
  3. vectorstore에서 path prefix 매칭으로 필터링 후 벡터 검색

---

## 1. 질문 4가지에 대한 현재 상태

### (1) 청크 메타데이터에 폴더/경로 정보가 있는가
**부분적으로만.** 폴더(경로) 전용 필드는 **없음.**
- `MarkdownLoader`가 파일 상대경로를 `Document.source`에 저장 (`rel = os.path.relpath`, 예: `projects/friday/foo.md`) — `core/loader/markdown_loader.py:17`
- 이 `source`(=파일 경로 전체)가 청크 및 Postgres `source` 컬럼 + metadata JSON에 저장됨 — `core/vector_store/postgres_store.py:53,59`
- 청크 metadata는 문서 metadata 복사뿐이라 비어 있음 — `core/chunker/fixed_size_chunker.py:28`
- **폴더 단위 `path`(`/projects/friday`)도, prefix 검색용 컬럼도 없음.** 대신 `team_id`, `sensitivity`, `owner_id`, `doc_id` 컬럼이 존재 — `postgres_store.py:23-27`

### (2) 권한을 검색 전/후에 거는가
**검색 "전"(pre-filter), 방향은 목표와 일치.** 단 거는 **축이 다름.**
- `permission_node` → `retrieve_node` 순서로, `build_pg_filter`가 만든 `where_clause`를 벡터 검색 SQL `WHERE`에 주입 — `app/graph/nodes/retrieve.py:42`, `postgres_store.py:86`
- 필터 축이 **폴더 경로가 아니라** `sensitivity`/`team_id`/`doc_id` — `core/fga/client.py:17-38`

### (3) OpenFGA를 쓰는가, 어떤 모델인가
**씀.** 단 모델이 목표와 **완전히 다름.**
- 현재 모델 (`fga/model.fga`):
  ```
  type user
  type team       → member: [user]
  type document   → owner, viewer: [user:*, user, team#member] or owner
  ```
- `ListObjects`는 "사용자의 team 목록"을 받는 용도로만 사용 (`_list_fga_objects(user, member, team)`) — `client.py:65,81`
- 권한은 **2-tier pre-filter**: ① `team_id + sensitivity` ② 개인 `personal_doc_ids`(secret 문서는 `user_doc_grants` 테이블, per-user) — `client.py:24-36,69-77`
- **부서(department)·폴더(folder) 타입도, 트리 상속(`can_read from parent`)도 없음.** 대신 sensitivity 등급 + 개인 grant 개념이 존재.

### (4) 검색 흐름이 LangGraph 노드로 나뉘어 있는가
**예, 잘 나뉘어 있음.** — `app/graph/builder.py:76-93`
```
START → load_memory → rewrite_query → router
  └(doc_search)→ permission → retrieve → grade_documents → ...
```
`permission_node`(권한 조회)와 `retrieve_node`(필터+검색)가 별도 노드. **이 골격은 목표 흐름과 그대로 매핑됨.**

---

## 2. 차이 정리표

| 항목 | 현재 상태 | 목표 상태 | 관련 파일 | 판정 |
|---|---|---|---|---|
| 권한 주체 | 부서(team) + **개인 단위**(personal_docs, secret per-user grant) | **부서 단위만**, 개인 메타 없음 | `core/fga/client.py:31-36,69-77,148-163` | 🔴 갈아엎기 |
| OpenFGA 모델 | user / team / document(+sensitivity) | user / **department** / **folder**(parent·viewer·can_read 트리 상속) | `fga/model.fga`, `fga/model.json` | 🔴 갈아엎기 |
| 권한 등급(sensitivity) | public/internal/secret 자동 분류 + 필터 분기 | **없음** (폴더 권한으로 대체) | `core/fga/sensitivity.py`, `client.py:22-36`, `core/indexer/indexer.py:38` | 🔴 제거 |
| 권한 → 검색 연결 | `ListObjects(team)` → team_id/sensitivity WHERE | `ListObjects(can_read, folder)` → **상위 노드 추림** → **path prefix** WHERE | `client.py:64-67`, `nodes/permission.py`, `nodes/retrieve.py:42` | 🟡 골격 유지·내용 교체 |
| 상위 노드 추림(parent dedup) | **없음** | 부모가 있으면 자식 경로 버림 | (신규 필요) | 🔴 신규 |
| 청크 path 메타데이터 | `source`=파일 전체경로만, 폴더 path 필드 없음 | 청크에 `path`(`/projects/friday`) 저장 | `core/chunker/fixed_size_chunker.py:28`, `core/indexer/indexer.py:39-43` | 🟡 path 도출 추가 |
| 벡터 필터 컬럼 | `team_id, sensitivity, owner_id, doc_id` | `path`(prefix 매칭) | `postgres_store.py:23-27,86` | 🔴 스키마 교체 |
| pre-filter 메커니즘 | where_clause를 벡터 SQL에 주입 (정상 동작) | 동일 메커니즘 (축만 path) | `retrieve.py:42`, `postgres_store.py:86` | 🟢 살림 |
| LangGraph 노드 분리 | permission → retrieve 분리됨 | 동일 구조 | `builder.py:57-65,92` | 🟢 살림 |

---

## 3. 살릴 수 있는 부분 🟢 / 🟡

- **LangGraph 노드 골격** (`permission → retrieve` 분리): 그대로 재사용. 두 노드의 **내용만** 교체.
- **pre-filter 주입 메커니즘**: `build_pg_filter` → `where_clause` → 벡터 검색 SQL `WHERE`. 구조 완벽. **필터 축만** sensitivity/team → path prefix로 교체.
- **FGAClient 인프라**: 캐시 계층(`PermissionCacheBackend`, TTL), `ListObjects` 호출·예외처리·tuple write 로직. **relation/type만** (`member,team` → `can_read,folder`) 바꾸면 재활용 가능.
- **Postgres vector store / BasicRetriever / RRF merge / reranker**: 검색 엔진 자체는 유지. 컬럼 정의만 조정.
- **MarkdownLoader의 `source`(relpath)**: path 메타 도출의 원천으로 재활용 (파일경로 → 폴더 path 변환).

## 4. 갈아엎어야 하는 부분 🔴

1. **OpenFGA 모델 전면 교체** (`fga/model.fga`, `fga/model.json`): team/document → department/folder + 트리 상속.
2. **sensitivity 전체 제거**: `core/fga/sensitivity.py`, `core/indexer/indexer.py`의 등급 부여, `build_pg_filter`의 sensitivity 분기.
3. **개인 단위 권한 제거**: `personal_docs`, `user_doc_grants` 테이블, secret 처리, `_query_personal_docs`/`_insert_personal_doc` 등.
4. **`build_pg_filter` 재작성**: team/sensitivity/doc_id → path prefix.
5. **`permission_node` 재작성**: team 목록 → can_read folder 목록 + **상위 노드 추림 로직 신규**.
6. **Indexer 메타 부여**: team_id/sensitivity → path.
7. **Postgres 스키마**: `team_id/sensitivity/owner_id/doc_id` 컬럼 → `path` 컬럼 (+ prefix 인덱스).
8. **`AgentState`**: `user_teams`/`personal_doc_ids` → `allowed_folders` 류로 — `app/graph/state.py:22-24`.

---

## 5. 주의 (아키텍처 결정 변경)

- CLAUDE.md에는 "FGA: 2-tier pre-filter, listObjects 전체 목록 미사용"이라 적혀 있으나, 목표(DESIGN.md)는 **정반대로 `ListObjects`로 폴더 목록을 받는 방식**.
- 이 핵심 아키텍처 결정이 뒤집히므로, 코드 작업 전에 **`backend/CLAUDE.md`의 FGA 섹션 + ADR(`docs/superpowers/decisions/`)도 함께 갱신** 필요.
