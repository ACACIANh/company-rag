# 도구 라벨 자동 표시 + capability 감사 요약 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 응답 상단에 사용된 도구(rag/sql/permission/audit)를 자동 발견 방식으로 라벨 표시하고, 관리자의 capability 안내 응답에 감사로그 건수 요약을 덧붙인다.

**Architecture:** 도구 레지스트리(`app/graph/tools/registry.py`)를 라벨의 단일 진실원천(SSOT)으로 삼는다. 각 `ToolAgent`가 클래스 속성 `label`을 self-declare하고, `tool_label_map()`이 이를 자동 수집한다. 응답 조립부(`builder.py`)에서 `route`+`agent_messages`로부터 사용 도구 라벨을 계산해 `Answer.tools` / 스트리밍 `sources` 이벤트로 전달한다. 감사 요약은 `AuditSink.count_by_decision()` 집계를 `capability_node`가 관리자일 때만 호출해 본문에 덧붙인다.

**Tech Stack:** Python 3.11 / LangGraph / FastAPI / asyncpg / pytest (backend), Vite + React + TypeScript (frontend).

작업 디렉토리 규칙: 백엔드 명령은 `backend/`에서, 인터프리터는 `.venv/bin/python`. 프론트 명령은 `web/`에서.

---

## 파일 구조 (생성/수정)

**백엔드**
- 수정 `backend/app/graph/tools/base.py` — `ToolAgent` 프로토콜에 `label: str`
- 수정 `backend/app/graph/tools/sql_tool.py` — `SqlAgent.label = "sql"`
- 수정 `backend/app/graph/tools/permission_tool.py` — `PermissionAgent.label = "permission"`
- 수정 `backend/app/graph/tools/audit_history_tool.py` — `AuditAgent.label = "audit"`
- 수정 `backend/app/graph/tools/registry.py` — `tool_label_map()` 추가
- 생성 `backend/app/graph/tool_labels.py` — `collect_tool_labels(route, agent_messages)`
- 수정 `backend/core/models.py` — `Answer.tools`
- 수정 `backend/app/graph/builder.py` — `answer_question`/`stream_answer`에서 라벨 계산·전달, `capability` 노드에 `audit_sink` 주입
- 수정 `backend/app/api/chat.py` — `ChatResponse.tools`
- 수정 `backend/core/observability/audit/base.py` — `AuditSink.count_by_decision()`
- 수정 `backend/core/observability/audit/postgres_sink.py` — `count_by_decision` 구현
- 수정 `backend/app/graph/nodes/capability_node.py` — 관리자 감사 요약
- 생성 `backend/tests/app/graph/test_tool_labels.py`
- 생성 `backend/tests/app/graph/tools/test_registry.py`
- 수정 `backend/tests/app/graph/nodes/test_capability_node.py`
- 수정 `backend/tests/core/observability/audit/test_postgres_sink.py`

**프론트엔드**
- 수정 `web/src/types.ts` — `ChatMessage.tools`, `SSEEvent` sources에 `tools`, `ChatResponse.tools`
- 수정 `web/src/chat/ChatPage.tsx` — sources 이벤트에서 `tools` 수신
- 생성 `web/src/chat/ToolHeader.tsx` — 상단 도구 헤더
- 수정 `web/src/chat/MessageList.tsx` — assistant 메시지 상단에 `ToolHeader`

**문서**
- 생성 ADR 2건, 수정 `backend/CLAUDE.md`, 재생성 `decisions/README.md`

---

## Task 1: ToolAgent 라벨 self-declare + 레지스트리 라벨 맵

**Files:**
- Modify: `backend/app/graph/tools/base.py:10-12`
- Modify: `backend/app/graph/tools/sql_tool.py:41-42`
- Modify: `backend/app/graph/tools/permission_tool.py:41-42`
- Modify: `backend/app/graph/tools/audit_history_tool.py` (클래스 `AuditAgent` 선언부)
- Modify: `backend/app/graph/tools/registry.py`
- Test: `backend/tests/app/graph/tools/test_registry.py` (create)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/app/graph/tools/test_registry.py` 생성:

```python
from app.graph.tools.registry import tool_label_map


def test_tool_label_map_covers_all_registered_tools():
    labels = tool_label_map()
    assert labels["query_business_data"] == "sql"
    assert labels["manage_permission"] == "permission"
    assert labels["audit_history"] == "audit"


def test_tool_label_map_values_are_short_role_labels():
    # 외부 노출 라벨은 역할(role) 기반 소문자 단어 (ADR-0033)
    for label in tool_label_map().values():
        assert label.islower()
        assert " " not in label
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'tool_label_map'`

- [ ] **Step 3: ToolAgent 프로토콜에 label 추가**

`backend/app/graph/tools/base.py`의 클래스 본문(현재 `name: str` 줄 아래)에 추가:

```python
@runtime_checkable
class ToolAgent(Protocol):
    name: str
    label: str
```

- [ ] **Step 4: 각 도구에 label 클래스 속성 추가**

`backend/app/graph/tools/sql_tool.py` (`class SqlAgent:` 본문, `name` 줄 아래):

```python
class SqlAgent:
    name = "query_business_data"
    label = "sql"
```

`backend/app/graph/tools/permission_tool.py` (`class PermissionAgent:` 본문):

```python
class PermissionAgent:
    name = "manage_permission"
    label = "permission"
```

`backend/app/graph/tools/audit_history_tool.py` (`class AuditAgent:` 선언부, `name` 줄 아래에 동일 패턴):

```python
    name = "audit_history"
    label = "audit"
```

> 참고: `AuditAgent`의 `name` 정의 위치를 먼저 확인하고 바로 아래에 `label`을 둔다. (다른 두 도구와 동일하게 클래스 속성)

- [ ] **Step 5: registry.py에 tool_label_map 추가**

`backend/app/graph/tools/registry.py`에 import 아래(파일 끝)로 추가:

```python
# 도구 라벨 SSOT: 등록된 도구 클래스에서 name→label 자동 수집 (ADR 후속).
# 새 도구 추가 = _TOOL_CLASSES에 한 줄 + 클래스에 label 선언. 수동 매핑 테이블 없음.
_TOOL_CLASSES = (SqlAgent, PermissionAgent, AuditAgent)


def tool_label_map() -> dict[str, str]:
    """도구명(name) → 역할 라벨(label) 맵. 응답 조립부가 사용 도구를 라벨로 변환할 때 사용."""
    return {cls.name: cls.label for cls in _TOOL_CLASSES}
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: 커밋**

```bash
git add app/graph/tools/base.py app/graph/tools/sql_tool.py app/graph/tools/permission_tool.py app/graph/tools/audit_history_tool.py app/graph/tools/registry.py tests/app/graph/tools/test_registry.py
git commit -m "feat(tools): ToolAgent label self-declare + tool_label_map SSOT"
```

---

## Task 2: 사용 도구 라벨 계산 헬퍼

**Files:**
- Create: `backend/app/graph/tool_labels.py`
- Test: `backend/tests/app/graph/test_tool_labels.py` (create)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/app/graph/test_tool_labels.py` 생성:

```python
from langchain_core.messages import AIMessage

from app.graph.tool_labels import collect_tool_labels


def test_doc_search_route_returns_rag():
    assert collect_tool_labels("doc_search", []) == ["rag"]


def test_capability_route_returns_empty():
    assert collect_tool_labels("capability", []) == []


def test_agent_route_maps_tool_calls_to_labels():
    msgs = [
        AIMessage(content="", tool_calls=[
            {"name": "query_business_data", "args": {}, "id": "1"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "audit_history", "args": {}, "id": "2"},
        ]),
    ]
    assert collect_tool_labels("agent", msgs) == ["sql", "audit"]


def test_agent_route_dedupes_preserving_order():
    msgs = [
        AIMessage(content="", tool_calls=[
            {"name": "audit_history", "args": {}, "id": "1"},
            {"name": "query_business_data", "args": {}, "id": "2"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "audit_history", "args": {}, "id": "3"},
        ]),
    ]
    assert collect_tool_labels("agent", msgs) == ["audit", "sql"]


def test_agent_route_ignores_unknown_tool_names():
    msgs = [AIMessage(content="", tool_calls=[{"name": "ghost", "args": {}, "id": "1"}])]
    assert collect_tool_labels("agent", msgs) == []


def test_non_aimessage_entries_are_skipped():
    # 도구 결과 ToolMessage 등 tool_calls 없는 메시지는 무시
    from langchain_core.messages import HumanMessage
    msgs = [HumanMessage(content="hi")]
    assert collect_tool_labels("agent", msgs) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_tool_labels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.graph.tool_labels'`

- [ ] **Step 3: 헬퍼 구현**

`backend/app/graph/tool_labels.py` 생성:

```python
"""사용 도구 라벨 계산 (응답 상단 헤더용).

route + agent_messages에서 실제 호출된 도구를 역할 라벨 목록으로 변환한다.
doc_search 라우트는 도구가 아니라 RAG 검색이므로 ["rag"]로 매핑한다(라벨 SSOT의 한 곳 예외).
agent 라우트는 tool_label_map()으로 도구명→라벨을 자동 변환한다(중복 제거, 첫 등장 순서 유지).
"""
from app.graph.tools.registry import tool_label_map


def collect_tool_labels(route: str, agent_messages: list) -> list[str]:
    if route == "doc_search":
        return ["rag"]
    if route != "agent":
        return []
    label_map = tool_label_map()
    labels: list[str] = []
    for msg in agent_messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            label = label_map.get(name)
            if label and label not in labels:
                labels.append(label)
    return labels
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_tool_labels.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/graph/tool_labels.py tests/app/graph/test_tool_labels.py
git commit -m "feat(graph): collect_tool_labels — route+agent_messages를 도구 라벨로 변환"
```

---

## Task 3: Answer.tools + 응답/스트리밍 전달 + ChatResponse

**Files:**
- Modify: `backend/core/models.py:30-34`
- Modify: `backend/app/graph/builder.py:207,243,325-329`
- Modify: `backend/app/api/chat.py:131-134,180`
- Test: `backend/tests/app/graph/test_builder.py` (기존 — 변경 영향 없음, 회귀로만 확인)

- [ ] **Step 1: Answer 데이터클래스에 tools 필드 추가**

`backend/core/models.py`의 `Answer`를 수정 (이미 `field`는 import됨):

```python
@dataclass
class Answer:
    text: str
    sources: list[SourceRef]
    trace: list[dict] | None = None
    tools: list[str] = field(default_factory=list)
```

- [ ] **Step 2: builder.py에 헬퍼 import 추가**

`backend/app/graph/builder.py` 상단 import 블록(`from app.graph.state import AgentState` 위)에 추가:

```python
from app.graph.tool_labels import collect_tool_labels
```

- [ ] **Step 3: answer_question 두 반환 경로에 tools 채우기**

`backend/app/graph/builder.py`의 resume 완료 경로(현재 207행)를:

```python
        if "__interrupt__" in final:
            return _interrupt_answer(final)
        return Answer(
            text=final.get("answer", ""),
            sources=final.get("citations", []),
            tools=collect_tool_labels(final.get("route", "doc_search"), final.get("agent_messages", [])),
        )
```

그리고 일반 반환 경로(현재 243행)를:

```python
    final = await graph.ainvoke(initial, config={**config, "recursion_limit": 25})
    if "__interrupt__" in final:
        return _interrupt_answer(final)
    return Answer(
        text=final["answer"],
        sources=final["citations"],
        tools=collect_tool_labels(final.get("route", "doc_search"), final.get("agent_messages", [])),
    )
```

- [ ] **Step 4: stream_answer sources 이벤트에 tools 추가**

`backend/app/graph/builder.py`의 sources 이벤트(현재 325-329행)를:

```python
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
            "route": final.get("route", "doc_search"),
            "tools": collect_tool_labels(final.get("route", "doc_search"), final.get("agent_messages", [])),
        })
```

- [ ] **Step 5: ChatResponse에 tools 추가 + 채우기**

`backend/app/api/chat.py`의 `ChatResponse`(131행):

```python
class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str
    tools: list[str] = []
```

반환부(180행):

```python
    return ChatResponse(
        answer=result.text,
        sources=[s.source for s in result.sources],
        session_id=session_id,
        tools=result.tools,
    )
```

- [ ] **Step 6: 회귀 테스트 — builder/모델 전체**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py tests/core -q`
Expected: PASS (기존 테스트 그대로 통과 — Answer 추가 필드는 기본값이라 비파괴적)

- [ ] **Step 7: 커밋**

```bash
git add core/models.py app/graph/builder.py app/api/chat.py
git commit -m "feat(api): 응답에 사용 도구 라벨(tools) 전달 — 비스트리밍/스트리밍"
```

---

## Task 4: 프론트엔드 도구 상단 헤더

**Files:**
- Modify: `web/src/types.ts:22-26,40-48,73-79`
- Modify: `web/src/chat/ChatPage.tsx:100-107`
- Create: `web/src/chat/ToolHeader.tsx`
- Modify: `web/src/chat/MessageList.tsx:131-159`

> 검증은 타입체크/빌드로 한다(`web`에 단위 테스트 러너 미가정). 모든 명령은 `web/`에서 실행.

- [ ] **Step 1: 타입 정의 확장**

`web/src/types.ts`의 `ChatResponse`(22행)에 `tools` 추가:

```typescript
export interface ChatResponse {
  answer: string;
  sources: string[];
  session_id: string;
  tools?: string[];
}
```

`ChatMessage`(40행)에 `tools` 추가:

```typescript
export interface ChatMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
  route?: string;
  tools?: string[];
  streaming?: boolean;
  interrupt?: InterruptAction[];
  clarify?: ClarifyPayload;
}
```

`SSEEvent`의 sources 변형(75행)에 `tools` 추가:

```typescript
  | { type: "sources";   sources: string[]; route?: string; tools?: string[] }
```

- [ ] **Step 2: ToolHeader 컴포넌트 생성**

`web/src/chat/ToolHeader.tsx` 생성 (라벨은 백엔드에서 온 문자열을 그대로 대문자 표기 — 새 도구 추가 시 프론트 수정 불필요, 자동 전파):

```tsx
export function ToolHeader({ tools }: { tools: string[] }) {
  if (!tools || tools.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-1 px-1">
      <span className="text-[10px] text-ink-mute font-light">🔧 도구</span>
      {tools.map((t) => (
        <span
          key={t}
          className="text-[10px] font-normal bg-primary-muted text-primary-deep px-2 py-0.5 rounded-pill tracking-[0.1px] uppercase"
        >
          {t}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: ChatPage 스트림 핸들러에서 tools 수신**

`web/src/chat/ChatPage.tsx`의 sources 이벤트 처리(104행)를:

```tsx
        } else if (event.type === "sources") {
          if (assistantAdded) {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = {
                ...next[next.length - 1],
                sources: event.sources,
                route: event.route,
                tools: event.tools,
              };
              return next;
            });
          }
```

- [ ] **Step 4: MessageList에서 assistant 메시지 상단에 헤더 렌더링**

`web/src/chat/MessageList.tsx` 상단 import에 추가:

```tsx
import { ToolHeader } from "./ToolHeader";
```

assistant/user 공통 렌더 블록(현재 131행 `return ( <div key={idx} ...`)에서 **메시지 버블 div 바로 위**에 헤더를 넣는다. 즉 `<div className={msg.role === "user" ? ... : ...}>` (140행의 버블 div) 직전에 삽입:

```tsx
        return (
          <div
            key={idx}
            className={
              msg.role === "user"
                ? "self-end max-w-[75%]"
                : "self-start w-full max-w-[92%]"
            }
          >
            {msg.role === "assistant" && !msg.streaming && msg.tools && msg.tools.length > 0 && (
              <ToolHeader tools={msg.tools} />
            )}
            <div
              className={
                msg.role === "user"
                  ? "bg-brand-dark text-canvas rounded-xl px-4 py-3 text-[15px] font-light"
                  : "bg-canvas border border-hairline rounded-xl px-4 py-3 text-[15px] font-light text-ink"
              }
```

(이후 기존 코드 그대로. SourceBadge 등 하단 블록은 변경하지 않는다.)

- [ ] **Step 5: 타입체크/빌드 확인**

Run (in `web/`): `npm run build`
Expected: 빌드 성공, 타입 에러 없음

- [ ] **Step 6: 커밋**

```bash
git add web/src/types.ts web/src/chat/ToolHeader.tsx web/src/chat/ChatPage.tsx web/src/chat/MessageList.tsx
git commit -m "feat(web): 답변 상단에 사용 도구 헤더(ToolHeader) 표시"
```

---

## Task 5: AuditSink.count_by_decision 집계

**Files:**
- Modify: `backend/core/observability/audit/base.py:25-27`
- Modify: `backend/core/observability/audit/postgres_sink.py`
- Test: `backend/tests/core/observability/audit/test_postgres_sink.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/core/observability/audit/test_postgres_sink.py`에 추가. 먼저 파일 상단 `_make_pool` 헬퍼는 `conn.execute`만 모킹하므로, fetch용 헬퍼를 새로 추가:

```python
def _make_pool_with_fetch(rows):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_count_by_decision_groups_by_decision():
    rows = [
        {"gate_decision": "ALLOW", "n": 15},
        {"gate_decision": "DENY", "n": 3},
        {"gate_decision": "JUSTIFY_AND_APPROVE", "n": 5},
    ]
    pool, conn = _make_pool_with_fetch(rows)
    sink = PostgresAuditSink(pool)

    counts = await sink.count_by_decision()

    assert counts == {"ALLOW": 15, "DENY": 3, "JUSTIFY_AND_APPROVE": 5}
    sql = conn.fetch.call_args[0][0].upper()
    assert "GROUP BY GATE_DECISION" in sql
    assert "FROM GATE_AUDIT_LOG" in sql


@pytest.mark.asyncio
async def test_count_by_decision_empty_returns_empty_dict():
    pool, _ = _make_pool_with_fetch([])
    sink = PostgresAuditSink(pool)
    assert await sink.count_by_decision() == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/observability/audit/test_postgres_sink.py -k count_by_decision -v`
Expected: FAIL — `AttributeError: 'PostgresAuditSink' object has no attribute 'count_by_decision'`

- [ ] **Step 3: ABC에 추상 메서드 추가**

`backend/core/observability/audit/base.py`의 `AuditSink`:

```python
class AuditSink(ABC):
    @abstractmethod
    async def record(self, record: AuditRecord) -> None: ...

    @abstractmethod
    async def count_by_decision(self) -> dict[str, int]:
        """gate_decision 값별 누적 건수. 예: {"ALLOW": 15, "DENY": 3}."""
        ...
```

- [ ] **Step 4: PostgresAuditSink에 구현 추가**

`backend/core/observability/audit/postgres_sink.py`의 `record` 메서드 아래에 추가:

```python
    async def count_by_decision(self) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT gate_decision, COUNT(*) AS n "
                "FROM gate_audit_log GROUP BY gate_decision"
            )
        return {r["gate_decision"]: r["n"] for r in rows}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/observability/audit/test_postgres_sink.py -v`
Expected: PASS (기존 + 신규 모두 통과)

- [ ] **Step 6: 커밋**

```bash
git add core/observability/audit/base.py core/observability/audit/postgres_sink.py tests/core/observability/audit/test_postgres_sink.py
git commit -m "feat(audit): AuditSink.count_by_decision 집계 추가"
```

---

## Task 6: capability_node 관리자 감사 요약 + builder 배선

**Files:**
- Modify: `backend/app/graph/nodes/capability_node.py:30-34`
- Modify: `backend/app/graph/builder.py:96`
- Test: `backend/tests/app/graph/nodes/test_capability_node.py`

- [ ] **Step 1: 실패 테스트 작성/수정**

`backend/tests/app/graph/nodes/test_capability_node.py`를 다음으로 교체(기존 2개 테스트는 `audit_sink` 키워드 추가로 호환 유지, 신규 2개 추가):

```python
from unittest.mock import AsyncMock, MagicMock

from app.graph.nodes.capability_node import capability_node


def _mock_fga(can_grant: bool) -> MagicMock:
    client = MagicMock()
    client.check = AsyncMock(return_value=can_grant)
    return client


def _mock_audit(counts: dict) -> MagicMock:
    sink = MagicMock()
    sink.count_by_decision = AsyncMock(return_value=counts)
    return sink


async def test_capability_node_admin_text_when_can_grant():
    fga_client = _mock_fga(True)

    result = await capability_node({"user_id": "joohwan"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:joohwan", "justify_grant", "capability:admin")
    assert "권한 관리" in result["answer"]
    assert "부여" in result["answer"]
    assert result["citations"] == []


async def test_capability_node_user_text_when_cannot_grant():
    fga_client = _mock_fga(False)

    result = await capability_node({"user_id": "minjun"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:minjun", "justify_grant", "capability:admin")
    assert "권한 확인" in result["answer"]
    assert "부여" not in result["answer"]
    assert result["citations"] == []


async def test_admin_gets_audit_summary_when_sink_present():
    fga_client = _mock_fga(True)
    audit = _mock_audit({"ALLOW": 15, "DENY": 3, "JUSTIFY_AND_APPROVE": 5})

    result = await capability_node({"user_id": "joohwan"}, fga_client=fga_client, audit_sink=audit)

    audit.count_by_decision.assert_awaited_once()
    assert "총 23건" in result["answer"]
    assert "ALLOW 15" in result["answer"]
    assert "DENY 3" in result["answer"]
    assert "JUSTIFY 5" in result["answer"]


async def test_non_admin_never_queries_audit():
    fga_client = _mock_fga(False)
    audit = _mock_audit({"ALLOW": 1})

    result = await capability_node({"user_id": "minjun"}, fga_client=fga_client, audit_sink=audit)

    audit.count_by_decision.assert_not_called()
    assert "총" not in result["answer"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_capability_node.py -v`
Expected: FAIL — 신규 2개에서 `count_by_decision` 미호출/요약 미포함 (`TypeError`는 없어야 함: 시그니처에 audit_sink 추가 후)

- [ ] **Step 3: capability_node 구현**

`backend/app/graph/nodes/capability_node.py` 하단(현재 `capability_node` 함수)을 교체:

```python
# 감사 요약: gate_decision 키 → 표시 라벨 (JUSTIFY_AND_APPROVE는 JUSTIFY로 축약)
_DECISION_LABELS = (("ALLOW", "ALLOW"), ("DENY", "DENY"), ("JUSTIFY_AND_APPROVE", "JUSTIFY"))


def _format_audit_summary(counts: dict) -> str:
    total = sum(counts.values())
    parts = " · ".join(f"{label} {counts.get(key, 0)}" for key, label in _DECISION_LABELS)
    return f"\n\n📊 최근 게이트 결정: 총 {total}건 ({parts})"


async def capability_node(state: dict, *, fga_client: FGAClient, audit_sink=None) -> dict:
    can_grant = await fga_client.check(
        f"user:{state['user_id']}", "justify_grant", "capability:admin"
    )
    if not can_grant:
        return {"answer": _TEXT_USER, "citations": []}
    answer = _TEXT_ADMIN
    if audit_sink is not None:
        counts = await audit_sink.count_by_decision()
        answer += _format_audit_summary(counts)
    return {"answer": answer, "citations": []}
```

- [ ] **Step 4: builder에서 audit_sink 주입**

`backend/app/graph/builder.py` 96행:

```python
    g.add_node("capability", partial(capability_node, fga_client=fga_client, audit_sink=audit_sink))
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_capability_node.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/graph/nodes/capability_node.py app/graph/builder.py tests/app/graph/nodes/test_capability_node.py
git commit -m "feat(capability): 관리자 안내에 감사로그 건수 요약 추가"
```

---

## Task 7: 전체 회귀 + ADR + CLAUDE.md

**Files:**
- Create: `backend/docs/superpowers/decisions/ADR-NNNN-tool-label-auto-discovery.md`
- Create: `backend/docs/superpowers/decisions/ADR-(NNNN+1)-capability-audit-summary.md`
- Modify: `backend/CLAUDE.md` (핵심 아키텍처 결정 섹션)
- Regenerate: `backend/docs/superpowers/decisions/README.md`

- [ ] **Step 1: 백엔드 전체 테스트 회귀**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS (실패 시 원인 분석 후 수정)

- [ ] **Step 2: eval 회귀 점수 확인 (DoD)**

Run: `.venv/bin/python -m tests.eval.runner`
Expected: 점수 출력. 라우팅/응답 변경이 아니므로 점수 하락 없어야 함. 하락 시 원인 명시.

- [ ] **Step 3: 다음 ADR 번호 확인**

Run: `ls docs/superpowers/decisions/ | grep -oE 'ADR-[0-9]+' | sort -t- -k2 -n | tail -1`
Expected: 현재 최대 번호 확인 → 다음 두 번호를 NNNN, NNNN+1로 사용

- [ ] **Step 4: ADR 2건 작성**

`docs/superpowers/decisions/_template.md`를 따라 두 파일 작성:
- `ADR-NNNN-tool-label-auto-discovery.md` — 제목 아래 `> **Status**: 🟢 적용완료`. 내용: 도구 라벨을 레지스트리 SSOT(`tool_label_map`)에서 자동 발견, 도구가 `label` self-declare, doc_search→rag는 라우트 단일 매핑, 응답 `Answer.tools`/스트리밍 `sources.tools`/프론트 `ToolHeader`로 전파. 대안(하드코딩 매핑 테이블) 기각 사유: 도구 추가 시 수동 동기화 부채.
- `ADR-(NNNN+1)-capability-audit-summary.md` — `> **Status**: 🟢 적용완료`. 내용: capability 안내 응답에서 관리자(can_grant)에게만 `count_by_decision` 집계로 게이트 결정 건수 요약을 본문에 덧붙임. 일반 사용자는 비노출(민감정보 보호). 형식은 건수 요약(목록 아님) — `audit_history` 도구가 상세 조회를 이미 제공하므로 중복 회피.

- [ ] **Step 5: CLAUDE.md 핵심 아키텍처 결정 섹션 갱신**

`backend/CLAUDE.md`의 "## 핵심 아키텍처 결정" 목록에 두 줄 추가(기존 명명 원칙 줄 근처):

```markdown
- 응답 도구 라벨: 사용 도구를 레지스트리 SSOT(`tool_label_map`)에서 자동 발견해 응답 상단 헤더로 표시(rag/sql/permission/audit). 새 도구는 `label` self-declare만으로 전파. 상세: ADR-NNNN.
- capability 안내 감사 요약: 관리자에게만 게이트 결정 건수 요약(`count_by_decision`)을 안내 본문에 덧붙임. 상세: ADR-(NNNN+1).
```

- [ ] **Step 6: ADR 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성 (직접 편집 금지)

- [ ] **Step 7: 커밋**

```bash
git add docs/superpowers/decisions/ CLAUDE.md
git commit -m "docs(adr): 도구 라벨 자동 발견 + capability 감사 요약 ADR"
```

---

## Self-Review 체크 결과

- **스펙 커버리지**: 요청 2(자동 라벨·상단 헤더) → Task 1~4. 요청 1(관리자 감사 요약) → Task 5~6. 자동 발견 구조 → Task 1(`tool_label_map`)+Task 2. DoD(테스트·eval·ADR) → 각 Task의 테스트 + Task 7. 누락 없음.
- **타입 일관성**: `tool_label_map() -> dict[str,str]`, `collect_tool_labels(route, agent_messages) -> list[str]`, `Answer.tools: list[str]`, `count_by_decision() -> dict[str,int]`, 프론트 `tools?: string[]` — 전 Task에서 명칭/시그니처 일치.
- **플레이스홀더**: 없음. ADR 본문만 Task 7에서 템플릿 기반 작성(번호는 Step 3에서 확정).
- **비파괴성**: `Answer.tools`·`ChatResponse.tools`는 기본값, `capability_node.audit_sink`는 기본 `None` → 기존 테스트/호출부 호환.
