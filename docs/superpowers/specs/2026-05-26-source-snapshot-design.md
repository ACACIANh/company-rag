# Source Snapshot — 세션 이력 FGA 재검증 설계

## 배경 및 문제

`GET /sessions/{id}/messages`로 과거 세션을 로드할 때, `chat_messages.sources`에 저장된
문자열 목록을 아무런 권한 검증 없이 그대로 반환한다.

**버그 시나리오**:
1. 사용자가 문서 X에 접근 가능한 상태로 질문 → "X"가 sources에 저장
2. 해당 사용자의 팀 멤버십 또는 문서 권한이 취소됨
3. 기존 세션 로드 → Source 배지에 "X"가 여전히 노출됨

새 `/chat` 응답은 `permission_node → retrieve_node` 경로에서 FGA 필터가 적용되므로
올바르게 동작한다. 문제는 세션 이력 로드 경로에만 해당된다.

## 설계 방향

저장 시점의 문서 메타데이터(sensitivity, team_id, document_id)를 **스냅샷**으로 함께
저장한다. 세션 이력 로드 시 스냅샷 메타데이터 + 현재 FGA 권한으로 재검증하여
접근 불가 source를 제거한다.

- 현재 권한이 기준 → 권한이 취소된 문서는 과거 이력에서도 숨김
- 추가 Chroma 쿼리 불필요 (메타데이터는 저장 시점에 이미 확보됨)
- FGA 조회는 기존 캐시(`get_permission`) 재사용

## 변경 범위

### 1. `shared/models.py` — SourceRef 추가

```python
@dataclass
class SourceRef:
    source: str           # 화면에 표시할 파일명 (기존 citations 값)
    document_id: str = ""
    sensitivity: str = "public"
    team_id: str = ""
```

`Answer.sources: list[str]` → `list[SourceRef]`

### 2. `shared/vector_store/chroma_store.py` — Chunk에 전체 메타데이터 전달

`search()` 에서 Chunk 생성 시:
```python
chunk = Chunk(
    text=doc,
    source=results["metadatas"][0][i]["source"],
    chunk_id=results["ids"][0][i],
    metadata=results["metadatas"][0][i],   # 추가 — sensitivity, team_id, document_id 포함
)
```

### 3. `app/graph/nodes/generate.py` — citations를 SourceRef로 생성

```python
from shared.models import SourceRef

citations = [
    SourceRef(
        source=d.chunk.source,
        document_id=d.chunk.metadata.get("document_id", ""),
        sensitivity=d.chunk.metadata.get("sensitivity", "public"),
        team_id=d.chunk.metadata.get("team_id", ""),
    )
    for d in state["documents"]
]
```

### 4. `app/graph/state.py` — citations 타입 변경

```python
from shared.models import SourceRef
# ...
citations: list[SourceRef]   # 기존: list[str]
```

### 5. `shared/session/base.py` — StoredMessage, SessionStore 시그니처 변경

```python
from shared.models import SourceRef

@dataclass
class StoredMessage:
    role: str
    content: str
    sources: list[SourceRef] = field(default_factory=list)   # 기존: list[str]

class SessionStore(ABC):
    @abstractmethod
    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None: ...
```

### 6. `shared/session/adapters/postgres.py` — JSONB 직렬화/역직렬화

저장:
```python
psycopg2.extras.Json([dataclasses.asdict(s) for s in sources])
```

로드 (구버전 string 형식 하위 호환):
```python
SourceRef(source=item) if isinstance(item, str) else SourceRef(**item)
```

DDL 변경 없음. `sources JSONB` 컬럼이 dict 배열을 그대로 수용.

### 7. `shared/session/adapters/memory.py`

`add_message` 시그니처를 `list[SourceRef]`로만 변경. 내부 로직 동일.

### 8. `shared/fga/client.py` — filter_sources 추가

```python
def filter_sources(self, sources: list[SourceRef], user_id: str) -> list[SourceRef]:
    perm = self.get_permission(user_id)   # 캐시 우선 사용
    return [s for s in sources if self._is_accessible(s, perm)]

def _is_accessible(self, src: SourceRef, perm: UserPermission) -> bool:
    if src.sensitivity == "public":
        return True
    if src.sensitivity == "internal":
        return src.team_id in perm.teams
    if src.sensitivity == "secret":
        return src.document_id in perm.personal_docs
    return False
```

### 9. `app/api/deps.py` — get_fga_client 추가

```python
def get_fga_client() -> FGAClient:
    ...   # build_graph() 내 _default_fga_client()와 동일 로직, lru_cache로 싱글턴
```

### 10. `app/api/sessions.py` — 세션 이력 로드 시 필터링

```python
@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    fga_client: FGAClient = Depends(get_fga_client),
):
    ...
    result = []
    for m in store.get_messages(session_id):
        if m.role == "assistant" and m.sources:
            visible = fga_client.filter_sources(m.sources, user["user_id"])
        else:
            visible = m.sources
        result.append(MessageOut(
            role=m.role,
            content=m.content,
            sources=[s.source for s in visible],
        ))
    return result
```

### 11. `app/api/chat.py` — ChatResponse sources 변환

```python
# 저장 시: list[SourceRef] 그대로 전달
store.add_message(session_id, "assistant", result.text, result.sources)

# 응답 시: 화면 표시용 문자열 변환 (ChatResponse.sources: list[str] 유지)
return ChatResponse(
    answer=result.text,
    sources=[s.source for s in result.sources],
    session_id=session_id,
)
```

## 프론트엔드

변경 없음. `ChatResponse.sources`와 `MessageOut.sources`가 모두 여전히 `list[str]`을
반환하므로 `SourceBadge`에 영향 없음.

## 하위 호환

- 기존 PostgreSQL `chat_messages.sources` 컬럼에 저장된 `["string", ...]` 형식은
  역직렬화 시 `SourceRef(source=item, sensitivity="public")`으로 업캐스트.
- public 문서는 모든 사용자가 접근 가능하므로 구버전 데이터도 올바르게 표시됨.
- internal/secret 구버전 데이터는 sensitivity="public"으로 처리되어 계속 표시.
  (수용 가능 — 기존 저장 데이터는 저장 당시 접근 가능했던 문서임)

## 테스트 계획

- `test_fga_client.py`: `filter_sources` 단위 테스트 (public/internal/secret 각 케이스)
- `test_generate.py`: `SourceRef` 포함 citations 생성 검증
- `test_session_store.py`: `add_message` / `get_messages` SourceRef 직렬화·역직렬화 (구버전 호환 포함)
- `test_sessions_api.py`: `GET /sessions/{id}/messages` — 권한 변경 후 source 필터링 검증
- 회귀: `tests/eval/runner.py` 실행, 점수 하락 시 원인 명시

## DoD

- [ ] 위 테스트 통과
- [ ] `tests/eval/runner.py` 회귀 점수 유지
- [ ] ADR 없음 (기존 FGA 전략 범위 내 구현)
