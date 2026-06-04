# Capability 역할 기반 동적 응답 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "할수 있는게 뭐야?" 질문에 대해 FGA `allow_grant@capability:admin` 보유 여부에 따라 권한 관리 섹션을 다르게 응답한다.

**Architecture:** `capability_node`를 async factory 패턴으로 전환하고 `fga_client`를 주입한다. `state["user_id"]`로 FGA Check를 수행해 `True`면 전체 권한 관리 텍스트, `False`면 권한 조회 텍스트만 반환한다. `builder.py`에서 `partial`로 주입.

**Tech Stack:** Python 3.11+, LangGraph, pytest-asyncio, `unittest.mock.AsyncMock`

---

## 파일 변경 맵

| 파일 | 변경 종류 | 내용 |
|------|-----------|------|
| `app/graph/nodes/capability_node.py` | Modify | async 전환, `_TEXT_USER`/`_TEXT_ADMIN` 분리, FGA check 추가 |
| `app/graph/builder.py` | Modify | `capability` 노드 등록 시 `fga_client` 주입 (1줄) |
| `tests/app/graph/nodes/test_capability_node.py` | Create | async 단위 테스트 2케이스 |

---

## Task 1: capability_node 테스트 작성

**Files:**
- Create: `tests/app/graph/nodes/test_capability_node.py`

- [ ] **Step 1: 테스트 파일 생성**

```python
# tests/app/graph/nodes/test_capability_node.py
from unittest.mock import AsyncMock, MagicMock

from app.graph.nodes.capability_node import capability_node


def _mock_fga(can_grant: bool) -> MagicMock:
    client = MagicMock()
    client.check = AsyncMock(return_value=can_grant)
    return client


async def test_capability_node_admin_text_when_can_grant():
    fga_client = _mock_fga(True)

    result = await capability_node({"user_id": "alice"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:alice", "allow_grant", "capability:admin")
    assert "권한 관리" in result["answer"]
    assert "부여" in result["answer"]
    assert result["citations"] == []


async def test_capability_node_user_text_when_cannot_grant():
    fga_client = _mock_fga(False)

    result = await capability_node({"user_id": "bob"}, fga_client=fga_client)

    fga_client.check.assert_called_once_with("user:bob", "allow_grant", "capability:admin")
    assert "권한 확인" in result["answer"]
    assert "부여" not in result["answer"]
    assert result["citations"] == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/test_capability_node.py -v
```

예상 결과: `FAILED` — `capability_node` is not a coroutine function (현재 sync 함수)

---

## Task 2: capability_node async 전환 및 FGA check 구현

**Files:**
- Modify: `app/graph/nodes/capability_node.py`

- [ ] **Step 3: capability_node.py 전체 교체**

```python
# app/graph/nodes/capability_node.py
from core.fga.client import FGAClient

_TEXT_USER = """저는 다음과 같은 작업을 도와드릴 수 있습니다.

**사내 문서 검색** — 정책·규정·절차·가이드 등 문서 기반 질문
예: "연차 사용 규정이 어떻게 돼?", "보안 정책 알려줘"

**업무 DB 조회** — 직원·매출 등 테이블 값 조회·집계
예: "영업팀 평균 급여 알려줘", "이번 분기 매출 상위 5개 부서는?"

**권한 확인** — 내 부서 소속 및 폴더 접근 권한 조회
예: "내 권한 알려줘", "나 어느 부서에 속해 있어?"

궁금한 게 있으면 바로 질문해 주세요!"""

_TEXT_ADMIN = """저는 다음과 같은 작업을 도와드릴 수 있습니다.

**사내 문서 검색** — 정책·규정·절차·가이드 등 문서 기반 질문
예: "연차 사용 규정이 어떻게 돼?", "보안 정책 알려줘"

**업무 DB 조회** — 직원·매출 등 테이블 값 조회·집계
예: "영업팀 평균 급여 알려줘", "이번 분기 매출 상위 5개 부서는?"

**권한 관리** — 부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수/조회
예: "alice를 engineering 부서에 추가해줘", "내 권한 알려줘", "finance 폴더 접근 권한 회수해줘"

궁금한 게 있으면 바로 질문해 주세요!"""


async def capability_node(state: dict, *, fga_client: FGAClient) -> dict:
    can_grant = await fga_client.check(
        f"user:{state['user_id']}", "allow_grant", "capability:admin"
    )
    return {"answer": _TEXT_ADMIN if can_grant else _TEXT_USER, "citations": []}
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/test_capability_node.py -v
```

예상 결과:
```
PASSED tests/app/graph/nodes/test_capability_node.py::test_capability_node_admin_text_when_can_grant
PASSED tests/app/graph/nodes/test_capability_node.py::test_capability_node_user_text_when_cannot_grant
2 passed
```

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/capability_node.py tests/app/graph/nodes/test_capability_node.py
git commit -m "feat: capability_node FGA 기반 역할별 응답 분기"
```

---

## Task 3: builder.py fga_client 주입

**Files:**
- Modify: `app/graph/builder.py:96`

- [ ] **Step 6: builder.py 노드 등록 1줄 수정**

`app/graph/builder.py` 에서 capability 노드 등록 라인을 찾아 변경:

```python
# Before (line ~96)
g.add_node("capability", capability_node)

# After
g.add_node("capability", partial(capability_node, fga_client=fga_client))
```

`partial`은 파일 상단에 이미 `from functools import partial` 로 import되어 있다. 확인 후 없으면 추가.

- [ ] **Step 7: 기존 builder 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/test_builder.py -v
```

예상 결과: 모든 테스트 PASSED (기존 테스트가 `fga_client=None` 또는 mock으로 builder를 호출한다면 `partial(capability_node, fga_client=None)` 형태가 되므로 테스트 시 `None` 처리가 있는지 확인 — 없다면 Step 8에서 처리)

- [ ] **Step 8: builder 테스트 실패 시 대처**

`test_builder.py`에서 `fga_client=None`으로 `build_graph`를 호출하는 경우, `capability_node`가 실제 실행될 때만 오류가 발생하므로 빌드 자체는 문제없다. 테스트가 capability 경로를 실행하는 경우에는 mock fga_client를 넣어줘야 한다. 실패 시 해당 테스트 케이스에 `MagicMock()`으로 `fga_client` 교체.

- [ ] **Step 9: 전체 노드 테스트 스위트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/ -v
```

예상 결과: 모든 노드 테스트 PASSED

- [ ] **Step 10: 커밋**

```bash
git add app/graph/builder.py
git commit -m "feat: capability 노드에 fga_client 주입"
```

---

## 완료 검증

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/test_capability_node.py tests/app/graph/test_builder.py -v
```

예상 결과: 신규 2개 + 기존 builder 테스트 모두 PASSED
