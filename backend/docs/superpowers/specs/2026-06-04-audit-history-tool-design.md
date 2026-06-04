# 감사 이력 조회 도구 설계 (audit_history_tool)

## 목표

관리자가 LangGraph ReAct 루프 안에서 자연어로 `gate_audit_log`를 조회할 수 있도록,
`query_audit_history` 도구를 기존 ToolHandler 패턴에 맞춰 추가한다.

---

## 도구 인터페이스

**도구명**: `query_audit_history`

**description** (LLM에 노출):
> 감사 이력(게이트 결정·SQL 실행 사유)을 조회합니다. 관리자 전용.
> 필터 조건(유저 ID, 결정 유형, 날짜 범위, 건수)을 자연어로 받아 최신순으로 반환합니다.

**파라미터** (LLM이 채움, 모두 선택):

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `limit` | int | 20 | 반환 건수. 최대 100으로 clamp |
| `user_id` | str \| None | None | 특정 유저 필터 |
| `decision` | str \| None | None | `ALLOW` / `DENY` / `JUSTIFY_AND_APPROVE` |
| `start_date` | str \| None | None | ISO 날짜 `YYYY-MM-DD` |
| `end_date` | str \| None | None | ISO 날짜 `YYYY-MM-DD` |

---

## 아키텍처 결정

### 방식: 기존 ToolHandler 패턴 (Approach A)

레지스트리에 `AuditHistoryToolHandler`를 추가해 agent → tool_gate → execute 흐름을 유지한다.
별도 노드나 그래프 엣지 변경 없음.

### 위험도: `RISK_SELECT` 재사용

`plan()`이 `RISK_SELECT`를 반환하면 gate가 `capability:sql allow_select` 보유 시 ALLOW 처리한다.
추가 위험도 상수나 FGA 튜플 불필요.

admin 체크는 `execute()` 안에서 `fga_client.user_roles(user_id)`로 수행한다.

### admin 판별

`fga_client.user_roles(user_id)` 반환 목록에 `"admin"`이 포함되면 관리자로 인정한다.
관리자 부여는 기존 `manage_permission` 도구(OpenFGA 튜플 write)로 처리한다.

---

## 데이터 흐름

```
agent_node
  └─ AIMessage(tool_calls=[{name:"query_audit_history", args:{...}}])

tool_gate_node
  ├─ plan(args) → (params_json, RISK_SELECT)
  ├─ gate_decision → ALLOW  (capability:sql allow_select 보유 시)
  └─ execute(params_json, RISK_SELECT)
       1. fga_client.user_roles(user_id) 조회
       2. "admin" 없으면 → "권한 없음" ToolMessage 반환
       3. params_json 파싱 → parameterized SELECT on gate_audit_log
       4. 포맷된 텍스트 → ToolMessage 반환

agent_node  ← ToolMessage 수신 후 최종 답변 생성
```

---

## 구현 구조

### 신규 파일

```
app/graph/tools/audit_history_tool.py
```

```python
class AuditHistoryToolHandler:
    name = "query_audit_history"

    def __init__(self, *, fga_client: FGAClient, app_pool: asyncpg.Pool) -> None: ...

    def plan(self, args: dict) -> tuple[str, str]:
        # args 파싱·검증 (limit clamp, decision 검증)
        # 반환: (params_json, RISK_SELECT)
        # 잘못된 decision 값 → (에러 메시지, RISK_DENY)

    async def execute(self, planned_action: str, risk: str) -> str:
        # 1. fga admin 체크
        # 2. params_json 파싱 → parameterized SQL
        # 3. gate_audit_log SELECT
        # 4. 포맷된 텍스트 반환
```

### 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `app/graph/tools/registry.py` | `AuditHistoryToolHandler` 등록, `build_tool_registry`에 `app_pool` 파라미터 추가 |
| `app/graph/builder.py` | `build_graph`에 `app_pool` 파라미터 추가, `build_tool_registry`로 전달 |
| `app/api/chat.py` | `build_graph(app_pool=pool, ...)` — 기존 앱 DB pool을 명시적으로 전달 |

> `core/sql/risk.py`, `core/sql/gate.py` 수정 없음 — `RISK_SELECT` 재사용.

---

## 에러 처리

| 상황 | 처리 |
|---|---|
| admin role 없음 | `"권한 없음: 감사 이력은 관리자만 조회할 수 있습니다."` ToolMessage |
| `limit` > 100 | 100으로 clamp (plan에서) |
| 잘못된 `decision` 값 | `plan()`에서 `RISK_DENY` 반환 → gate DENY |
| DB 오류 | `execute()`에서 예외 캐치 → 에러 메시지 ToolMessage |

---

## 테스트

파일: `tests/app/graph/tools/test_audit_history_tool.py`

- `plan()` 단위 테스트
  - 정상 파라미터 → `RISK_SELECT` 반환
  - `limit` > 100 → 100으로 clamp
  - 잘못된 `decision` → `RISK_DENY` 반환
- `execute()` 단위 테스트
  - 비관리자 → "권한 없음" 반환
  - 관리자 + AsyncMock pool → 결과 포맷 반환
  - DB 오류 → 에러 메시지 반환
- `test_builder.py`
  - `app_pool` 주입 케이스 추가

---

## 변경 범위 요약

- **신규**: `app/graph/tools/audit_history_tool.py`
- **수정**: `app/graph/tools/registry.py`, `app/graph/builder.py`
- **수정(소폭)**: `app/api/chat.py` — `build_graph(app_pool=pool)` 한 줄 추가
- **무변경**: `core/sql/risk.py`, `core/sql/gate.py`, 그래프 노드/엣지 전체

ADR 번호: 추후 ADR-0040 발행 예정.
