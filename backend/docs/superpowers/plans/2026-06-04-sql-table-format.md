# SQL 조회 결과 마크다운 표 포매팅 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQL 도구(`query_business_data`) 결과를 최종 사용자 응답에서 마크다운 표로 렌더링한다.

**Architecture:** `_format_rows()`가 반환하는 `ToolMessage` content를 proper markdown table로 바꾸고, 에이전트 시스템 프롬프트에 "표를 그대로 답변에 포함하라" 지시를 추가한다. LLM이 표를 재구성할 필요 없이 입력 그대로 출력하게 된다.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, asyncpg(mock), langchain-core

---

## 파일 맵

| 파일 | 역할 | 변경 종류 |
| --- | --- | --- |
| `app/graph/tools/sql_tool.py` | `_format_rows()` 출력 형식 수정 | Modify (lines 31-38) |
| `app/graph/nodes/agent.py` | `_SYSTEM` 프롬프트 1문장 추가 | Modify (lines 9-12) |
| `tests/app/graph/tools/test_sql_tool.py` | 표 형식 단위 테스트 추가 | Modify |

---

### Task 1: `_format_rows()` 표 형식 테스트 작성

**Files:**
- Modify: `tests/app/graph/tools/test_sql_tool.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/test_sql_tool.py` 맨 아래에 추가:

```python
# ── _format_rows 표 형식 테스트 ──────────────────────────────
from app.graph.tools.sql_tool import _format_rows


def test_format_rows_empty():
    assert _format_rows([]) == "(결과 없음)"


def test_format_rows_markdown_table_structure():
    rows = [{"name": "Alice", "salary": 5000}, {"name": "Bob", "salary": 6000}]
    result = _format_rows(rows)
    lines = result.splitlines()
    # 헤더 | 구분선 | 데이터 2행 = 4줄
    assert len(lines) == 4
    assert lines[0] == "| name | salary |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Alice | 5000 |"
    assert lines[3] == "| Bob | 6000 |"


def test_format_rows_single_column():
    rows = [{"count": 42}]
    result = _format_rows(rows)
    lines = result.splitlines()
    assert lines[0] == "| count |"
    assert lines[1] == "| --- |"
    assert lines[2] == "| 42 |"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && \
  .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py::test_format_rows_markdown_table_structure -v
```

예상 출력: `FAILED` — `ImportError: cannot import name '_format_rows'` 또는 `AssertionError`

---

### Task 2: `_format_rows()` 구현 수정

**Files:**
- Modify: `app/graph/tools/sql_tool.py:31-38`

- [ ] **Step 1: `_format_rows()` 본문 교체**

`app/graph/tools/sql_tool.py`의 `_format_rows` 함수(현재 lines 31-38)를 아래로 교체:

```python
def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    data_lines = ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join([header, separator, *data_lines])
```

- [ ] **Step 2: 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && \
  .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v
```

예상 출력: 모든 테스트 `PASSED` (기존 테스트 포함)

- [ ] **Step 3: 커밋**

```bash
git add app/graph/tools/sql_tool.py tests/app/graph/tools/test_sql_tool.py
git commit -m "feat(sql_tool): _format_rows 마크다운 표 형식으로 변경"
```

---

### Task 3: 에이전트 시스템 프롬프트 수정

**Files:**
- Modify: `app/graph/nodes/agent.py:9-12`

- [ ] **Step 1: `_SYSTEM` 1문장 추가**

`app/graph/nodes/agent.py`의 `_SYSTEM` 상수를 아래로 교체:

```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다."
)
```

- [ ] **Step 2: 기존 에이전트 테스트 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && \
  .venv/bin/python -m pytest tests/ -k "agent" -v
```

예상 출력: 에이전트 관련 테스트 모두 `PASSED`

- [ ] **Step 3: 커밋**

```bash
git add app/graph/nodes/agent.py
git commit -m "feat(agent): SQL 표 형식 보존 지시 시스템 프롬프트에 추가"
```

---

### Task 4: 전체 테스트 통과 확인

**Files:** 없음 (검증 단계)

- [ ] **Step 1: 전체 단위 테스트 실행**

```bash
cd /Users/acacian/vscode/company-rag/backend && \
  .venv/bin/python -m pytest tests/ -v --tb=short
```

예상 출력: 모든 테스트 `PASSED`, 실패 0건
