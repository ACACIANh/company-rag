# tool_call 에이전트화 (SP1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tool_call` 경로의 고정 SQL 서브루틴을, 게이트가 도구-실행-전 인터셉터로 동작하는 도구 불가지 ReAct 루프로 전환하고, JUSTIFY_AND_APPROVE HITL을 API 종단까지 재개 가능하게 만든다.

**Architecture:** 단일 ReAct 에이전트(LangChain `create_chat_llm().bind_tools()`)가 도구를 선택하면, `tool_gate` 노드가 도구별 `plan()`으로 위험도를 구체화하고 신원×위험도 게이트(`core/sql/gate.py`)로 ALLOW/JUSTIFY/DENY를 판정한 뒤 실행/HITL/거부한다. SQL은 첫 등록 도구(`query_business_data(question)`)로, 내부에서 기존 NL→SQL(값 힌트)·위험도 분류·read-only 실행을 재사용한다. 프리빌트 `create_react_agent`는 게이트 삽입을 위해 쓰지 않고 커스텀 그래프로 구성한다.

**Tech Stack:** Python 3.11+, LangGraph(StateGraph, interrupt), LangChain(`langchain_core.tools.Tool`, `create_chat_llm` = ChatAnthropic/ChatOpenAI `bind_tools`), sqlglot(기존 위험도), asyncpg(read-only 풀), pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-tool-call-agentification-design.md`

---

## 사전 메모 (실행자 필독)

- 작업 디렉토리는 항상 `backend/`. 인터프리터는 `.venv/bin/python`. 테스트: `.venv/bin/python -m pytest`.
- 레이어 규칙(CLAUDE.md): `core/`는 LangChain/LangGraph 불가지. 모든 LangChain `Tool`/`AnyMessage`/`bind_tools`는 `app/graph/`에 둔다. 게이트(`core/sql/gate.py`)·위험도(`core/sql/risk.py`)·감사(`core/observability/audit/`)는 순수 로직 그대로 재사용.
- `AgentState`는 `TypedDict` 확장만. `MessagesState`·익명 dict 금지.
- 기존 doc_search 경로(router→permission→retrieve→…)는 **건드리지 않는다**. 변경은 `tool_call` 분기에 한정.
- 두 LLM 경로 공존: 기존 노드는 `core.llm.LLMClient`(문자열), 에이전트 노드만 `create_chat_llm()`(chat).
- Phase A = ADR-0023(루프·레지스트리·인터셉터). Phase B = ADR-0024(HITL 종단). ADR 문서는 각 Phase 끝 태스크에서 작성.

---

# Phase A — ADR-0023: 게이트된 도구-디스패치 루프

## Task A0: langchain-anthropic 설치 + create_chat_llm 동작 확인

**Files:**
- 설치만(코드 변경 없음). 확인 대상: `core/llm/factory.py:create_chat_llm`

- [ ] **Step 1: 미설치 provider 패키지 설치**

`pyproject.toml`에 `langchain-anthropic>=1.0,<2`가 이미 선언돼 있으나 venv에 미설치다(`langchain-openai`는 설치됨). 운영 provider에 맞춰 설치한다.

Run: `.venv/bin/python -m pip install "langchain-anthropic>=1.0,<2"`
Expected: 설치 성공.

- [ ] **Step 2: create_chat_llm가 bind_tools 가능한 모델을 주는지 확인**

Run:
```bash
.venv/bin/python -c "
from core.config import load_config
from core.llm.factory import create_chat_llm
m = create_chat_llm(load_config())
assert hasattr(m, 'bind_tools'), 'chat model must support bind_tools'
print('create_chat_llm OK:', type(m).__name__)
"
```
Expected: `create_chat_llm OK: ChatOpenAI`(또는 ChatAnthropic). 에러 없이 통과.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): langchain-anthropic 설치 — create_chat_llm tool-calling 경로 활성화 (ADR-0023)"
```
(pyproject 변경이 없으면 빈 커밋 대신 생략하고 다음 태스크로.)

---

## Task A1: PendingToolCall 타입 + AgentState 확장

**Files:**
- Modify: `app/graph/state.py`
- Test: `tests/app/graph/test_state.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_state.py`에 추가:
```python
def test_agent_state_has_agentic_loop_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "agent_messages" in hints      # ADR-0023
    assert "pending_tool_calls" in hints   # ADR-0023
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_state.py::test_agent_state_has_agentic_loop_fields -v`
Expected: FAIL (KeyError/assert — 필드 없음).

- [ ] **Step 3: AgentState 확장**

`app/graph/state.py` 상단 import에 추가:
```python
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
```
`PendingToolCall` 타입 정의(파일 내 `AgentState` 위):
```python
class PendingToolCall(TypedDict):
    id: str               # tool_call_id
    name: str             # 도구명
    args: dict            # 도구 인자
    planned_action: str   # 구체화된 동작(SQL의 경우 생성된 SQL)
    risk: str             # core.sql.risk 등급
    decision: str         # ALLOW / DENY / JUSTIFY_AND_APPROVE
```
`AgentState`에 두 필드 추가(`justification` 줄 아래):
```python
    agent_messages: Annotated[list[AnyMessage], add_messages]  # 에이전트 도구 대화 (ADR-0023)
    pending_tool_calls: list[PendingToolCall]                   # interrupt를 넘는 in-flight 호출 (ADR-0023)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_state.py -v`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add app/graph/state.py tests/app/graph/test_state.py
git commit -m "feat(state): AgentState에 agent_messages·pending_tool_calls 추가 (ADR-0023)"
```

---

## Task A2: 도구 핸들러 추상화 (ToolHandler 프로토콜)

**Files:**
- Create: `app/graph/tools/__init__.py`
- Create: `app/graph/tools/base.py`
- Test: `tests/app/graph/tools/__init__.py`, `tests/app/graph/tools/test_base.py`

도구 = (LLM에 보일 LangChain `Tool` 정의) + (서버측 핸들러: `plan`/`execute`). `plan`은 인자를 구체화된 동작 + 위험도로 바꾸고, `execute`는 그 동작을 실행해 결과 텍스트를 만든다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/__init__.py`는 빈 파일로 생성. `tests/app/graph/tools/test_base.py`:
```python
from app.graph.tools.base import ToolHandler


class _DummyHandler:
    name = "echo"
    def plan(self, args):
        return (args["text"], "select")
    def execute(self, planned_action):
        return f"ran: {planned_action}"


def test_tool_handler_protocol_runtime_checkable():
    h = _DummyHandler()
    assert isinstance(h, ToolHandler)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    assert h.execute("hi") == "ran: hi"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v`
Expected: FAIL (ModuleNotFoundError: app.graph.tools.base).

- [ ] **Step 3: 구현**

`app/graph/tools/__init__.py`는 빈 파일. `app/graph/tools/base.py`:
```python
"""도구 핸들러 추상화 (ADR-0023) — app 계층(LangChain 인지).

도구 = LLM에 노출할 LangChain Tool 정의 + 서버측 핸들러(plan/execute).
plan은 인자를 '구체화된 동작 + 위험도'로 바꾼다(SQL이면 생성된 SQL + 위험도 등급).
execute는 그 동작을 실행해 결과 텍스트를 만든다. 게이트는 plan과 execute 사이에서 돈다.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolHandler(Protocol):
    name: str

    def plan(self, args: dict) -> tuple[str, str]:
        """도구 인자 → (구체화된 동작, core.sql.risk 위험도 등급)."""
        ...

    def execute(self, planned_action: str) -> str:
        """구체화된 동작 실행 → 결과 텍스트."""
        ...
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/tools/__init__.py app/graph/tools/base.py tests/app/graph/tools/
git commit -m "feat(tools): ToolHandler 프로토콜 추가 (ADR-0023)"
```

---

## Task A3: SQL 도구 핸들러 (query_business_data)

**Files:**
- Create: `app/graph/tools/sql_tool.py`
- Test: `tests/app/graph/tools/test_sql_tool.py`

기존 로직 재사용: NL→SQL은 `sql_generate_node`의 `_strip_code_fence` + `SQL_GENERATE_PROMPT`(값 힌트 포함), 위험도는 `classify_risk_node` 로직(AST + LLM 보강), 실행은 `sql_execute_node`의 행 포매팅.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/test_sql_tool.py`:
```python
from unittest.mock import MagicMock
import pytest

from app.graph.tools.sql_tool import SqlToolHandler


def test_plan_generates_sql_and_classifies_risk():
    llm = MagicMock()
    # 1) NL→SQL  2) 대량/PII 보강(no)
    llm.complete.side_effect = ["SELECT name FROM business.employees WHERE department = 'engineering'", "no"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"question": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"


def test_plan_bulk_pii_upgrades_risk():
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT salary FROM business.employees", "yes"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    _, risk = h.plan({"question": "전직원 급여"})
    assert risk == "bulk_select"


def test_name_and_tool_def():
    h = SqlToolHandler(llm=MagicMock(), sql_pool=MagicMock())
    assert h.name == "query_business_data"
    assert h.tool.name == "query_business_data"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현**

`app/graph/tools/sql_tool.py`:
```python
"""SQL 조회 도구 핸들러 (ADR-0023). NL 질문 → SQL → 위험도 → (게이트) → 실행.

NL→SQL·위험도 분류·결과 포매팅은 기존 노드 로직(ADR-0016/0017/0021)을 재사용한다.
실행은 read-only 제한계정 풀(ADR-0020)에서만 한다.
"""
import asyncpg
from langchain_core.tools import Tool

from core.llm.base import LLMClient
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, classify_sql_ast
from app.graph.prompts import SQL_GENERATE_PROMPT, SQL_BULK_PII_PROMPT
from app.graph.nodes.sql_generate import _strip_code_fence

_DEFAULT_ROW_LIMIT = 100

_DESCRIPTION = (
    "사내 업무 DB(business.employees, business.sales)의 레코드·집계 값을 조회한다. "
    "정책·규정 같은 문서 내용이 아니라 '테이블 값으로 답하는' 질문에만 쓴다. "
    "question 인자에 한국어 자연어 질문을 그대로 넣는다."
)


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join(str(r[c]) for c in cols))
    return "\n".join(lines)


class SqlToolHandler:
    name = "query_business_data"

    def __init__(self, *, llm: LLMClient, sql_pool: asyncpg.Pool, row_limit: int = _DEFAULT_ROW_LIMIT) -> None:
        self._llm = llm
        self._pool = sql_pool
        self._row_limit = row_limit
        # bind_tools용 정의. 실제 실행은 그래프가 핸들러로 라우팅하므로 func는 호출되지 않는다.
        self.tool = Tool(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda question: "",
        )

    def plan(self, args: dict) -> tuple[str, str]:
        question = args["question"]
        raw = self._llm.complete(SQL_GENERATE_PROMPT.format(question=question))
        sql = _strip_code_fence(raw)
        risk = classify_sql_ast(sql)
        if risk == RISK_SELECT:
            response = self._llm.complete(SQL_BULK_PII_PROMPT.format(sql=sql)).strip().lower()
            if response.startswith("yes"):
                risk = RISK_BULK_SELECT
        return sql, risk

    async def aexecute(self, planned_action: str) -> str:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(planned_action)
            return _format_rows(list(rows)[:self._row_limit])
        except Exception as exc:
            return f"SQL 실행 오류: {type(exc).__name__}"
```

> 참고: 실행은 비동기(asyncpg)라 `aexecute`로 둔다. `ToolHandler.execute`(동기) 시그니처와 다르므로, Task A5의 tool_gate는 핸들러에 `aexecute`가 있으면 await, 없으면 `execute`를 부르는 식으로 처리한다. (Step에서 명시)

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/tools/sql_tool.py tests/app/graph/tools/test_sql_tool.py
git commit -m "feat(tools): SqlToolHandler — NL 질문 → SQL plan/execute (ADR-0023)"
```

---

## Task A4: 도구 레지스트리

**Files:**
- Create: `app/graph/tools/registry.py`
- Test: `tests/app/graph/tools/test_registry.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/test_registry.py`:
```python
from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry


def test_registry_contains_sql_tool():
    reg = build_tool_registry(llm=MagicMock(), sql_pool=MagicMock())
    assert "query_business_data" in reg.handlers
    assert reg.handlers["query_business_data"].name == "query_business_data"
    names = [t.name for t in reg.tool_defs]
    assert "query_business_data" in names
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현**

`app/graph/tools/registry.py`:
```python
"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import Tool

from core.llm.base import LLMClient
from app.graph.tools.sql_tool import SqlToolHandler


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolHandler
    tool_defs: list[Tool]   # bind_tools용


def build_tool_registry(*, llm: LLMClient, sql_pool) -> ToolRegistry:
    sql = SqlToolHandler(llm=llm, sql_pool=sql_pool)
    handlers = {sql.name: sql}
    tool_defs = [sql.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/tools/registry.py tests/app/graph/tools/test_registry.py
git commit -m "feat(tools): 도구 레지스트리 (ADR-0023)"
```

---

## Task A5: agent 노드 (bind_tools)

**Files:**
- Create: `app/graph/nodes/agent.py`
- Test: `tests/app/graph/nodes/test_agent.py`

agent 노드는 `agent_messages`로 chat 모델을 호출한다. 첫 진입(agent_messages 비어있음)이면 시스템 지시 + 사용자 질문을 시드한다. 반환은 add_messages 리듀서가 누적하도록 `[ai_message]`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_agent.py`:
```python
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes.agent import agent_node


def test_agent_seeds_human_message_on_first_turn():
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="", tool_calls=[
        {"name": "query_business_data", "args": {"question": "전직원 급여"}, "id": "call_1"}
    ])
    out = agent_node({"agent_messages": [], "rewritten_question": "전직원 급여 보여줘"}, chat_model=model)
    # 시드된 HumanMessage + 응답 AIMessage가 누적된다
    msgs = out["agent_messages"]
    assert any(isinstance(m, HumanMessage) for m in msgs)
    assert any(isinstance(m, AIMessage) for m in msgs)
    # 모델에 넘긴 입력에 사용자 질문이 포함
    sent = model.invoke.call_args[0][0]
    assert any("전직원 급여 보여줘" in getattr(m, "content", "") for m in sent)


def test_agent_appends_ai_message_on_followup_turn():
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="최종 답변")
    out = agent_node(
        {"agent_messages": [HumanMessage(content="q")], "rewritten_question": "q"},
        chat_model=model,
    )
    assert out["agent_messages"][-1].content == "최종 답변"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_agent.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현**

`app/graph/nodes/agent.py`:
```python
"""ReAct 에이전트 노드 (ADR-0023). chat 모델이 도구를 선택하거나 최종 답변을 낸다.

chat_model은 build_graph에서 create_chat_llm(cfg).bind_tools(tool_defs)로 주입된다.
첫 진입이면 시스템 지시 + 사용자 질문을 agent_messages에 시드한다. 반환은 add_messages
리듀서가 누적한다.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다."
)


def agent_node(state: dict, *, chat_model) -> dict:
    messages = list(state.get("agent_messages") or [])
    seeded: list = []
    if not messages:
        question = state.get("rewritten_question") or state.get("question", "")
        seeded = [SystemMessage(content=_SYSTEM), HumanMessage(content=question)]
        messages = seeded
    ai: AIMessage = chat_model.invoke(messages)
    # 첫 턴이면 시드 메시지도 함께 누적해야 다음 턴에 보존된다.
    return {"agent_messages": [*seeded, ai]}
```

> 주의: add_messages 리듀서는 같은 id 메시지를 덮어쓴다. 시드 HumanMessage가 매 턴 중복되지 않도록, 첫 턴에만 seeded를 포함한다(위 구현은 messages가 비었을 때만 seeded를 채움).

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/agent.py tests/app/graph/nodes/test_agent.py
git commit -m "feat(agent): bind_tools 에이전트 노드 (ADR-0023)"
```

---

## Task A6: tool_gate 노드 — ALLOW/DENY 경로 (HITL은 A8에서)

**Files:**
- Create: `app/graph/nodes/tool_gate.py`
- Test: `tests/app/graph/nodes/test_tool_gate.py`

마지막 AIMessage의 tool_calls를 순회하며 각 호출을 plan→gate한다. 이 태스크에서는 ALLOW(실행)·DENY(거부 ToolMessage)만 처리하고, JUSTIFY는 pending_tool_calls에 적재만 한다(실행/HITL은 A8). 각 결정은 감사 로그에 남긴다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_tool_gate.py`:
```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.graph.nodes.tool_gate import tool_gate_node


def _fga(roles, depts):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=depts)
    return fga


def _handler(planned, risk, result="rows"):
    h = MagicMock()
    h.plan.return_value = (planned, risk)
    h.aexecute = AsyncMock(return_value=result)
    return h


def _registry(handler):
    reg = MagicMock()
    reg.handlers = {"query_business_data": handler}
    return reg


def _ai(tool_calls):
    return AIMessage(content="", tool_calls=tool_calls)


@pytest.mark.asyncio
async def test_allow_executes_and_appends_tool_message():
    handler = _handler("SELECT 1", "select", result="42")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c1"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),
    )
    msgs = out["agent_messages"]
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].tool_call_id == "c1"
    assert "42" in tool_msgs[0].content
    handler.aexecute.assert_awaited_once()


@pytest.mark.asyncio
async def test_deny_appends_rejection_without_executing():
    handler = _handler("UPDATE business.employees SET salary=0", "update_delete")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c2"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),   # general → UPDATE = DENY
    )
    tool_msgs = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].tool_call_id == "c2"
    assert "거부" in tool_msgs[0].content or "권한" in tool_msgs[0].content
    handler.aexecute.assert_not_called()


@pytest.mark.asyncio
async def test_justify_records_pending_without_executing():
    handler = _handler("SELECT salary FROM business.employees", "bulk_select")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c3"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),   # general → BULK = JUSTIFY
    )
    assert out["pending_tool_calls"]
    pend = out["pending_tool_calls"][0]
    assert pend["id"] == "c3" and pend["decision"] == "JUSTIFY_AND_APPROVE"
    handler.aexecute.assert_not_called()
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현**

`app/graph/nodes/tool_gate.py`:
```python
"""도구-실행-전 게이트 인터셉터 (ADR-0023).

에이전트가 부른 각 도구 호출을 plan으로 구체화(SQL의 경우 생성된 SQL+위험도)한 뒤,
신원×위험도 게이트(core.sql.gate)로 ALLOW/JUSTIFY/DENY를 판정한다. ALLOW는 즉시
실행해 ToolMessage를 만들고, DENY는 실행 없이 거부 ToolMessage를, JUSTIFY는
pending_tool_calls에 적재만 한다(HITL은 confirm/justify_execute에서). 모든 결정은
감사 로그(ADR-0018)에 남긴다.
"""
from langchain_core.messages import AIMessage, ToolMessage

from core.fga.client import FGAClient
from core.observability.audit.base import AuditRecord, AuditSink
from core.sql.gate import (
    identity_tier, gate_lookup,
    DECISION_ALLOW, DECISION_DENY, DECISION_JUSTIFY_AND_APPROVE,
)

_DENY_TEXT = "거부됨: 현재 권한으로 실행할 수 없는 요청입니다."


def _last_tool_calls(messages: list) -> tuple[AIMessage | None, list]:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return m, m.tool_calls
    return None, []


async def _execute(handler, planned_action: str) -> str:
    if hasattr(handler, "aexecute"):
        return await handler.aexecute(planned_action)
    return handler.execute(planned_action)


async def tool_gate_node(state: dict, *, registry, fga_client: FGAClient, audit_sink: AuditSink) -> dict:
    user_id = state["user_id"]
    roles = await fga_client.user_roles(user_id)
    departments = await fga_client.user_departments(user_id)
    tier = identity_tier(roles, departments)

    _, tool_calls = _last_tool_calls(state.get("agent_messages") or [])
    new_messages: list = []
    pending: list = []

    for tc in tool_calls:
        handler = registry.handlers.get(tc["name"])
        if handler is None:
            new_messages.append(ToolMessage(content="알 수 없는 도구", tool_call_id=tc["id"]))
            continue
        planned_action, risk = handler.plan(tc["args"])
        decision, reason = gate_lookup(tier, risk)

        await audit_sink.record(AuditRecord(
            user_id=user_id, department=",".join(departments), role=",".join(roles),
            question=state.get("question", ""), generated_sql=planned_action,
            sql_risk=risk, gate_decision=decision, reason=reason,
            result_summary="", thread_id=state.get("thread_id", ""),
        ))

        if decision == DECISION_ALLOW:
            result = await _execute(handler, planned_action)
            new_messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        elif decision == DECISION_DENY:
            new_messages.append(ToolMessage(content=_DENY_TEXT, tool_call_id=tc["id"]))
        else:  # JUSTIFY_AND_APPROVE
            pending.append({
                "id": tc["id"], "name": tc["name"], "args": tc["args"],
                "planned_action": planned_action, "risk": risk, "decision": decision,
            })

    out: dict = {}
    if new_messages:
        out["agent_messages"] = new_messages
    out["pending_tool_calls"] = pending
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/tool_gate.py tests/app/graph/nodes/test_tool_gate.py
git commit -m "feat(agent): tool_gate 인터셉터 — ALLOW/DENY/JUSTIFY 판정 (ADR-0023)"
```

---

## Task A7: 엣지 라우팅 (agent 분기 + tool_gate 후 분기)

**Files:**
- Modify: `app/graph/edges.py`
- Test: `tests/app/graph/test_edges.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_edges.py`에 추가:
```python
from langchain_core.messages import AIMessage
from app.graph.edges import route_after_agent, route_after_tool_gate


def test_route_after_agent_to_tool_gate_when_tool_calls():
    ai = AIMessage(content="", tool_calls=[{"name": "query_business_data", "args": {}, "id": "c1"}])
    assert route_after_agent({"agent_messages": [ai]}) == "tool_gate"


def test_route_after_agent_to_done_when_no_tool_calls():
    ai = AIMessage(content="최종 답변")
    assert route_after_agent({"agent_messages": [ai]}) == "agent_done"


def test_route_after_tool_gate_to_confirm_when_pending():
    assert route_after_tool_gate({"pending_tool_calls": [{"id": "c1"}]}) == "confirm"


def test_route_after_tool_gate_back_to_agent_when_no_pending():
    assert route_after_tool_gate({"pending_tool_calls": []}) == "agent"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_edges.py -k "after_agent or after_tool_gate" -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: 구현**

`app/graph/edges.py` 끝에 추가:
```python
def route_after_agent(state: dict) -> str:
    """에이전트 응답에 도구 호출이 있으면 게이트로, 없으면 최종 답변 종료 (ADR-0023)."""
    messages = state.get("agent_messages") or []
    for m in reversed(messages):
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls is not None:
            return "tool_gate" if tool_calls else "agent_done"
    return "agent_done"


def route_after_tool_gate(state: dict) -> str:
    """JUSTIFY 대기 호출이 있으면 confirm(HITL), 없으면 에이전트로 복귀 (ADR-0023)."""
    return "confirm" if state.get("pending_tool_calls") else "agent"
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_edges.py -v`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add app/graph/edges.py tests/app/graph/test_edges.py
git commit -m "feat(edges): route_after_agent·route_after_tool_gate (ADR-0023)"
```

---

## Task A8: confirm 노드 재배치 + justify_execute 노드 (HITL 실행)

**Files:**
- Modify: `app/graph/nodes/confirm.py`
- Create: `app/graph/nodes/justify_execute.py`
- Test: `tests/app/graph/nodes/test_confirm.py`(갱신), `tests/app/graph/nodes/test_justify_execute.py`

confirm은 pending_tool_calls의 계획된 동작(SQL)을 interrupt 페이로드에 노출하고 사유를 받는다(ADR-0027 유지). justify_execute는 사유가 있으면 pending을 실행해 ToolMessage를 만들고, 없으면 거부 ToolMessage를 만든 뒤 pending을 비운다.

- [ ] **Step 1: 실패 테스트 작성 (confirm 갱신)**

`tests/app/graph/nodes/test_confirm.py`의 기존 테스트를 pending_tool_calls 기반으로 갱신. 추가:
```python
def test_confirm_exposes_planned_action_in_interrupt():
    from unittest.mock import patch
    from app.graph.nodes.confirm import confirm_node
    with patch("app.graph.nodes.confirm.interrupt", return_value="감사 목적") as mi:
        out = confirm_node({"pending_tool_calls": [
            {"id": "c1", "name": "query_business_data", "args": {"question": "전직원 급여"},
             "planned_action": "SELECT salary FROM business.employees", "risk": "bulk_select",
             "decision": "JUSTIFY_AND_APPROVE"}
        ]})
    payload = str(mi.call_args[0][0])
    assert "SELECT salary FROM business.employees" in payload   # 계획된 SQL 노출
    assert out["confirmed"] is True and out["justification"] == "감사 목적"
```

`tests/app/graph/nodes/test_justify_execute.py`:
```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import ToolMessage

from app.graph.nodes.justify_execute import justify_execute_node


def _registry():
    h = MagicMock()
    h.aexecute = AsyncMock(return_value="급여 결과")
    reg = MagicMock(); reg.handlers = {"query_business_data": h}
    return reg, h


@pytest.mark.asyncio
async def test_executes_pending_when_justified():
    reg, h = _registry()
    state = {
        "confirmed": True, "justification": "사유",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select"}],
        "user_id": "u1",
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock())
    tms = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tms[0].tool_call_id == "c1" and "급여 결과" in tms[0].content
    assert out["pending_tool_calls"] == []
    h.aexecute.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejects_pending_when_not_justified():
    reg, h = _registry()
    state = {
        "confirmed": False, "justification": "",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select"}],
        "user_id": "u1",
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock())
    tms = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert "취소" in tms[0].content or "거부" in tms[0].content
    assert out["pending_tool_calls"] == []
    h.aexecute.assert_not_called()
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_confirm.py tests/app/graph/nodes/test_justify_execute.py -v`
Expected: FAIL.

- [ ] **Step 3: confirm 재작성**

`app/graph/nodes/confirm.py`:
```python
"""사유 기재 자가승인 노드 (ADR-0027, 0023 재배치).

pending_tool_calls의 계획된 동작(SQL 등)을 interrupt 페이로드에 노출하고 사유를
받는다. resume 값은 사유 문자열, 빈 사유는 통과 안 함(미기재 = 실행 안 함).
"""
from langgraph.types import interrupt


def confirm_node(state: dict) -> dict:
    pending = state.get("pending_tool_calls") or []
    actions = [
        {"tool": p["name"], "args": p.get("args", {}), "planned_action": p["planned_action"], "risk": p["risk"]}
        for p in pending
    ]
    response = interrupt({
        "message": "다음 작업은 사유 기재 후 본인 책임으로 실행됩니다. 실행 사유를 입력하세요.",
        "actions": actions,
    })
    justification = response.strip() if isinstance(response, str) else ""
    return {"confirmed": bool(justification), "justification": justification}
```

- [ ] **Step 4: justify_execute 구현**

`app/graph/nodes/justify_execute.py`:
```python
"""JUSTIFY 사유 입력 후 실행/거부 노드 (ADR-0023/0027).

confirm에서 사유를 받았으면 pending 도구호출을 실행해 ToolMessage를, 빈 사유면 취소
ToolMessage를 만든다. 실행 후 pending을 비우고 에이전트로 복귀한다. 사유는 감사 로그에 남긴다.
"""
from langchain_core.messages import ToolMessage

from core.observability.audit.base import AuditRecord, AuditSink

_CANCEL_TEXT = "취소됨: 사유가 입력되지 않아 실행하지 않았습니다."


async def _execute(handler, planned_action: str) -> str:
    if hasattr(handler, "aexecute"):
        return await handler.aexecute(planned_action)
    return handler.execute(planned_action)


async def justify_execute_node(state: dict, *, registry, audit_sink: AuditSink) -> dict:
    pending = state.get("pending_tool_calls") or []
    justified = bool(state.get("confirmed")) and bool((state.get("justification") or "").strip())
    messages: list = []

    for p in pending:
        handler = registry.handlers.get(p["name"])
        if justified and handler is not None:
            result = await _execute(handler, p["planned_action"])
            messages.append(ToolMessage(content=result, tool_call_id=p["id"]))
            reason = state.get("justification", "")
        else:
            messages.append(ToolMessage(content=_CANCEL_TEXT, tool_call_id=p["id"]))
            reason = "취소(사유 미기재)"
        await audit_sink.record(AuditRecord(
            user_id=state.get("user_id", ""), department="", role="",
            question=state.get("question", ""), generated_sql=p["planned_action"],
            sql_risk=p["risk"], gate_decision=p["decision"], reason=reason,
            result_summary="", thread_id=state.get("thread_id", ""),
        ))

    return {"agent_messages": messages, "pending_tool_calls": []}
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_confirm.py tests/app/graph/nodes/test_justify_execute.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/confirm.py app/graph/nodes/justify_execute.py tests/app/graph/nodes/test_confirm.py tests/app/graph/nodes/test_justify_execute.py
git commit -m "feat(agent): confirm에 계획 노출 + justify_execute 실행/거부 (ADR-0023/0027)"
```

---

## Task A9: 최종 답변 노드 (agent_done → answer 추출)

**Files:**
- Create: `app/graph/nodes/agent_answer.py`
- Test: `tests/app/graph/nodes/test_agent_answer.py`

에이전트 루프가 도구 없이 끝나면 마지막 AIMessage 내용을 `answer`로, citations는 빈 리스트(또는 도구 출처)로 둔다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_agent_answer.py`:
```python
from langchain_core.messages import AIMessage, HumanMessage
from app.graph.nodes.agent_answer import agent_answer_node


def test_extracts_final_answer_from_last_ai_message():
    state = {"agent_messages": [HumanMessage(content="q"), AIMessage(content="조회 결과 요약")]}
    out = agent_answer_node(state)
    assert out["answer"] == "조회 결과 요약"
    assert out["citations"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_agent_answer.py -v`
Expected: FAIL.

- [ ] **Step 3: 구현**

`app/graph/nodes/agent_answer.py`:
```python
"""에이전트 최종 답변 추출 노드 (ADR-0023).

도구 호출 없이 끝난 에이전트 루프의 마지막 AIMessage 내용을 answer로 싣는다.
SQL 도구 결과는 이미 agent_messages에 반영돼 LLM이 요약했으므로 별도 generate 불필요.
"""
from langchain_core.messages import AIMessage


def agent_answer_node(state: dict) -> dict:
    text = ""
    for m in reversed(state.get("agent_messages") or []):
        if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
            text = m.content
            break
    return {"answer": text, "citations": []}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_agent_answer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/agent_answer.py tests/app/graph/nodes/test_agent_answer.py
git commit -m "feat(agent): 최종 답변 추출 노드 (ADR-0023)"
```

---

## Task A10: 그래프 재배선 (tool_call 분기를 에이전트 루프로 교체)

**Files:**
- Modify: `app/graph/builder.py`
- Test: `tests/app/graph/test_builder.py`(갱신)

기존 `sql_generate/classify_risk/gate/sql_execute/sql_reject` 고정 노드 배선을 제거하고, 에이전트 루프로 교체한다. router의 tool_call 목적지를 `agent`로 바꾼다. 노드 함수 파일(sql_generate 등)은 SqlToolHandler가 로직을 재사용하므로 **삭제하지 않는다**(학습/재사용, CLAUDE.md 규칙 5) — 그래프 등록만 제거.

- [ ] **Step 1: 실패 테스트 작성/갱신**

`tests/app/graph/test_builder.py`의 SQL 게이트 통합 테스트들을 에이전트 루프 기준으로 갱신. 예: `test_tool_call_justify_triggers_interrupt`는 chat 모델 mock(`build_graph`에 주입 가능한 chat_model 인자)으로 tool_call 발생→JUSTIFY→interrupt를 확인. (chat_model 주입 인자 추가 필요 — Step 3에서 build_graph에 `chat_model: Any = None` 파라미터 추가, None이면 create_chat_llm 사용.)

최소 신규 테스트:
```python
@pytest.mark.asyncio
async def test_tool_call_allow_runs_through_agent_loop():
    from unittest.mock import AsyncMock, MagicMock
    from langchain_core.messages import AIMessage
    chat = MagicMock()
    chat.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "query_business_data",
            "args": {"question": "엔지니어링 부서원"}, "id": "c1"}]),
        AIMessage(content="엔지니어링 부서원은 N명입니다."),
    ]
    sql_llm = MagicMock()
    sql_llm.complete.side_effect = ["SELECT name FROM business.employees WHERE department='engineering'", "no"]
    graph = build_graph(
        retriever=_make_retriever(), llm=sql_llm,
        fga_client=_mock_fga_client(departments=["sales"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), chat_model=chat,
    )
    # router가 tool_call로 가도록 sql_llm.complete에 rewrite/router 응답도 필요 →
    # 기존 헬퍼 패턴(_make_initial_state)과 side_effect 순서를 맞춘다.
```
> 이 통합 테스트는 mock 시퀀스 조정이 까다롭다. 실행자는 기존 test_builder의 mock 패턴(rewrite→router→… 순서)을 따라 side_effect를 구성하고, 단발 ALLOW 경로가 agent→tool_gate→agent→agent_answer로 흐르는지 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -v`
Expected: FAIL (router가 아직 sql_generate로 감 / 신규 노드 미배선).

- [ ] **Step 3: builder 재배선**

`app/graph/builder.py` 변경:
1. import: `from app.graph.nodes.agent import agent_node`, `tool_gate_node`, `justify_execute_node`, `agent_answer_node`, `from app.graph.tools.registry import build_tool_registry`, `from core.llm.factory import create_chat_llm`, `from core.config import load_config`. edges에 `route_after_agent, route_after_tool_gate` 추가. `route_after_gate`/`route_after_confirm`는 SQL 전용이었으면 제거하거나 유지(아래 4 참고).
2. `build_graph` 시그니처에 `chat_model: Any = None` 추가. 본문 초입:
```python
    if chat_model is None:
        chat_model = create_chat_llm(load_config())
    registry = build_tool_registry(llm=llm, sql_pool=sql_pool)
    bound = chat_model.bind_tools(registry.tool_defs)
```
3. tool_call 노드 등록 교체 — 기존 sql_generate/classify_risk/gate/sql_execute/sql_reject `add_node`/edge 제거, 신규 등록:
```python
    g.add_node("agent", partial(agent_node, chat_model=bound))
    g.add_node("tool_gate", partial(tool_gate_node, registry=registry, fga_client=fga_client, audit_sink=audit_sink))
    g.add_node("confirm", confirm_node)
    g.add_node("justify_execute", partial(justify_execute_node, registry=registry, audit_sink=audit_sink))
    g.add_node("agent_answer", agent_answer_node)
```
4. router 분기: `"tool_call": "agent"`로 변경. 루프 배선:
```python
    g.add_conditional_edges("agent", route_after_agent,
        {"tool_gate": "tool_gate", "agent_done": "agent_answer"})
    g.add_conditional_edges("tool_gate", route_after_tool_gate,
        {"confirm": "confirm", "agent": "agent"})
    g.add_edge("confirm", "justify_execute")
    g.add_edge("justify_execute", "agent")
    g.add_edge("agent_answer", "save_memory")
```
5. 제거: `sql_generate→classify_risk→gate→…` 관련 `add_node`/`add_conditional_edges`/`add_edge` 전부. `route_after_gate`/`route_after_confirm` import도 미사용이면 제거. (confirm_node는 재사용하므로 유지.)
6. `recursion_limit`: compile 후 호출부에서 config에 `{"recursion_limit": 12}`를 넣거나, ainvoke config에 추가. answer_question/stream_answer의 `graph.ainvoke(initial, config=config)`를 `graph.ainvoke(initial, config={**config, "recursion_limit": 12})`로.
7. 초기 상태(initial dict) 두 곳에 `"agent_messages": [], "pending_tool_calls": []` 추가. 더 이상 안 쓰는 `generated_sql/sql_risk/gate_decision/justification`은 호환 위해 남겨도 무방(잔존 필드).

- [ ] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -20` 후 `.venv/bin/python -m pytest -q`
Expected: 신규/갱신 테스트 PASS, 기존 doc_search 테스트 무영향 PASS. (구 SQL 노드 단위 테스트 중 그래프 배선에 의존하던 것은 갱신/제거.)

- [ ] **Step 5: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(graph): tool_call 분기를 게이트된 에이전트 루프로 재배선 (ADR-0023)"
```

---

## Task A11: ADR-0023 작성 + 인덱스 재생성

**Files:**
- Create: `docs/superpowers/decisions/ADR-0023-tool-call-agentic-loop.md`
- Modify: `docs/superpowers/decisions/README.md`(자동 생성)

- [ ] **Step 1: ADR 작성**

`_template.md`를 따라 ADR-0023 작성. Status `🟢 적용완료`. 내용: 토폴로지 A 채택, LangChain Tool/bind_tools 도입, 게이트를 도구-실행-전 인터셉터로 재배치, AgentState 확장, create_react_agent 미사용 이유, SQL 도구 NL 입력. 영향받는 결정: ADR-0016/0017/0021/0027. 메모리 옛 0023~0026 스케치를 본 2분할(0023/0024)로 대체, 0025/0026 결번 명시.

- [ ] **Step 2: 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `생성 완료: ... README.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/decisions/ADR-0023-tool-call-agentic-loop.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0023 tool_call 에이전트 루프 (🟢 적용완료)"
```

---

# Phase B — ADR-0024: HITL 종단 완결 (API resume)

## Task B1: API resume 루프 — /chat

**Files:**
- Modify: `app/graph/builder.py`(answer_question에 resume 분기), `app/api/chat.py`
- Test: `tests/app/api/test_chat_resume.py`(신규), `tests/app/graph/test_builder.py`

interrupt 상태 스레드에 다음 메시지가 오면 그것을 **사유**로 해석해 `Command(resume=사유)`로 재개한다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/test_builder.py`에 resume 헬퍼 동작 테스트 추가, 또는 `answer_question`가 interrupt 상태를 감지해 Command resume로 재개하는지 검증:
```python
@pytest.mark.asyncio
async def test_answer_question_resumes_when_thread_interrupted():
    # 1) 첫 호출에서 JUSTIFY interrupt 발생 → 결과에 interrupt 노출
    # 2) 같은 thread로 두 번째 호출(사유 메시지) → Command(resume=사유)로 재개되어 실행 답변
    ...
```
> 실행자는 Task A10의 통합 테스트 mock 패턴을 재사용해 interrupt→resume 2-콜 시나리오를 구성한다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -k resume -v`
Expected: FAIL.

- [ ] **Step 3: answer_question에 resume 분기 구현**

`app/graph/builder.py` `answer_question` 상단을 수정:
```python
    config = _ensure_thread_id(config)
    existing = await graph.aget_state(config)
    # interrupt(JUSTIFY 사유 대기) 상태면 이번 입력을 사유로 해석해 재개 (ADR-0024)
    if existing.next and existing.tasks and any(t.interrupts for t in existing.tasks):
        from langgraph.types import Command
        final = await graph.ainvoke(Command(resume=question), config={**config, "recursion_limit": 12})
        return Answer(text=final.get("answer", ""), sources=final.get("citations", []))
```
(이후 기존 신규 질문 처리 로직.)

- [ ] **Step 4: interrupt 노출 — answer_question 반환 형태**

interrupt가 발생하면 `final`에 `__interrupt__`가 담긴다. `answer_question`이 이를 감지해 사용자에게 "사유 입력 필요 + 계획된 동작"을 담은 Answer로 변환:
```python
    final = await graph.ainvoke(initial, config={**config, "recursion_limit": 12})
    if "__interrupt__" in final:
        intr = final["__interrupt__"][0].value
        actions = intr.get("actions", [])
        text = "이 작업은 사유 기재 후 실행됩니다. 실행하려면 사유를 회신하세요.\n" + \
               "\n".join(f"- {a['tool']}: {a['planned_action']}" for a in actions)
        return Answer(text=text, sources=[])
    return Answer(text=final["answer"], sources=final["citations"])
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(api): JUSTIFY interrupt 노출 + 사유 회신 resume (answer_question, ADR-0024)"
```

---

## Task B2: API resume 루프 — /chat/stream

**Files:**
- Modify: `app/graph/builder.py`(stream_answer)
- Test: `tests/app/graph/test_builder.py`

- [ ] **Step 1: 실패 테스트 작성**

stream_answer가 interrupt 상태에서 사유로 재개하고, interrupt 발생 시 토큰 큐에 "사유 필요" 안내+`__interrupt__` 신호를 넣는지 검증.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -k stream -v`
Expected: FAIL.

- [ ] **Step 3: 구현**

`stream_answer`에 answer_question과 동일한 resume 감지/interrupt 처리 분기를 추가. interrupt면 토큰 큐에 `{"type": "interrupt", "actions": [...]}` + done을 넣고 종료.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/graph/builder.py tests/app/graph/test_builder.py
git commit -m "feat(api): 스트리밍 경로 JUSTIFY interrupt/resume (stream_answer, ADR-0024)"
```

---

## Task B3: 전체 회귀 + eval

**Files:** 없음(검증).

- [ ] **Step 1: 전체 테스트**

Run: `.venv/bin/python -m pytest -q`
Expected: 전체 PASS.

- [ ] **Step 2: eval 회귀(가능 시)**

doc_search 무영향 확인. eval 러너는 외부 LLM/DB 필요 — 환경이 되면 실행, 안 되면 "tool_call 한정 변경이라 doc_search eval 무영향"을 근거로 생략 기록.

- [ ] **Step 3: Commit (없으면 생략)**

---

## Task B4: ADR-0024 작성 + 메모리 갱신

**Files:**
- Create: `docs/superpowers/decisions/ADR-0024-hitl-api-resume.md`
- Modify: `docs/superpowers/decisions/README.md`, 메모리 `project_next_agentic_tools.md`

- [ ] **Step 1: ADR-0024 작성**

Status `🟢 적용완료`. 내용: interrupt 페이로드에 계획된 동작 노출, API resume 루프(answer_question/stream_answer), 사유=다음 사용자 메시지 해석, tool_call_id 매칭. 영향: ADR-0023/0027.

- [ ] **Step 2: 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`

- [ ] **Step 3: 메모리 갱신**

`~/.claude/.../memory/project_next_agentic_tools.md`에 SP1 완료(ADR-0023/0024) 기록, SP2(권한 도구)를 다음 작업으로.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/decisions/
git commit -m "docs(adr): ADR-0024 HITL API resume 종단 (🟢 적용완료)"
```

---

## Self-Review 메모 (작성자)

- **Spec 커버리지**: 도구 레지스트리(A2/A4)·게이트 인터셉터(A6)·루프(A5/A7/A9/A10)·HITL 종단(A8/B1/B2)·AgentState(A1)·SQL NL 입력(A3)·ADR 분해(A11/B4) 모두 태스크 존재. ✓
- **타입 일관성**: `PendingToolCall` 키(id/name/args/planned_action/risk/decision)가 A1·A6·A8에서 동일. `ToolHandler`는 `plan`/`execute`, SQL은 비동기라 `aexecute` 추가 — tool_gate/justify_execute의 `_execute` 헬퍼가 `aexecute` 우선 처리(A3 주석·A6/A8 구현 일치). ✓
- **주의(실행자)**: ① add_messages 리듀서와 시드 메시지 중복 — agent_node가 첫 턴에만 시드. ② 통합 테스트(A10/B1/B2)는 mock side_effect 순서가 까다로움 — 기존 test_builder 패턴을 따를 것. ③ LangChain/LangGraph 버전별 `tool_calls`/`interrupt`/`aget_state().tasks[].interrupts` API 형태는 실행 시 확인·미세조정. ④ create_chat_llm는 동기 `invoke` 사용(agent_node) — async 그래프에서 블로킹 우려 시 `ainvoke`로 교체 검토.
