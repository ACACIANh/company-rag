# PermissionAgent 개명 + 권한 조회(query) 기능 추가 설계

**Date**: 2026-06-04

## 배경 및 목표

현재 `app/graph/tools/`의 에이전트 클래스들이 `*ToolHandler` 접미사를 사용하고
있으나, 이들은 `plan() → gate → execute()` ReAct 루프를 직접 구현하는 **에이전트**다.
명칭과 역할이 불일치한다(ADR-0033 캡슐화 기반 명명 표준 위반).

동시에, 현재 `PermissionAgent`(구 `PermissionToolHandler`)는 grant/revoke만 지원하고
"내 권한이 뭐야?", "alice 접근 가능한 폴더 알려줘" 같은 조회 기능이 없다.
이 두 문제를 한 번에 해결한다.

## 변경 범위

### 1. `*ToolHandler` → `*Agent` 전면 개명

| 파일 | 기존 | 변경 |
|------|------|------|
| `base.py` | `ToolHandler` (Protocol) | `ToolAgent` |
| `sql_tool.py` | `SqlToolHandler` | `SqlAgent` |
| `permission_tool.py` | `PermissionToolHandler` | `PermissionAgent` |
| `audit_history_tool.py` | `AuditHistoryToolHandler` | `AuditAgent` |
| `registry.py` | import + 인스턴스화 + 주석 | 일괄 반영 |
| `tests/` | 모든 `*ToolHandler` import/참조 | 일괄 반영 |

`ToolRegistry.handlers` 타입 주석 `# name -> ToolHandler` → `# name -> ToolAgent`.

### 2. `PermissionAgent.plan()` — `query` 액션 추가

`plan()`이 LLM으로 instruction을 파싱할 때 `action` 필드를
`grant | revoke | query` 세 가지로 인식한다.

#### query 분기 로직 (plan — sync)

`plan()`은 sync이므로 FGA 호출 없이 파싱과 위험도 분류만 한다.
관리자 확인은 async인 `execute()`에서 수행한다(`AuditAgent` 동일 패턴).

```
plan(args):  # sync
  instruction → LLM 파싱 → {action, target_user_id}
  caller = args.get("__caller_id", "")

  if action == "query":
      target = parsed.get("target_user_id") or caller   # None → 본인
      return f"query {caller} {target}", RISK_SELECT
      # gate: RISK_SELECT → ALLOW 자동. 세밀한 접근제어는 execute()에서.

  else:  # grant | revoke — 기존 로직 유지
      ...
      return f"{action} {subject} {relation} {object_}", RISK_GRANT | RISK_DENY
```

#### execute() — query 분기 (async)

```
execute(planned_action, risk):  # async
  if planned_action.startswith("query "):
      _, caller, target = planned_action.split(" ", 2)
      if target != caller:
          admin_ok = await fga.check(f"user:{caller}", "member", "capability:admin")
          if not admin_ok:
              return "권한 없음: 타인 조회는 관리자만 가능합니다."
      departments = await fga.user_departments(target)
      roles       = await fga.user_roles(target)
      folders     = await fga.get_readable_folders(target)
      return _format_permission_snapshot(target, departments, roles, folders)

  else:  # grant | revoke — 기존 로직 유지
      ...
```

#### 출력 포맷 (`_format_permission_snapshot`)

```
사용자: alice
소속 부서: engineering, product
역할(role): admin
접근 가능 폴더(3개):
  - /engineering/specs
  - /engineering/runbooks
  - /shared/onboarding
```

### 3. 도구 description 갱신

`PermissionAgent`의 `_DESCRIPTION`에 조회 기능을 추가한다:

> "사내 접근 권한을 조회·부여·회수한다: 부서 멤버십, 폴더 접근권, SQL 실행 권한 등급.
> 예: '내 접근 가능한 폴더 알려줘', 'alice 권한 조회', '앨리스를 엔지니어링 부서에 추가'."

### 4. PERMISSION_PARSE_PROMPT 갱신

`query` 액션 few-shot 예시 추가 및 `target_user_id` 필드 파싱 지시 추가.

## 데이터 흐름

```
사용자: "내 접근 권한 알려줘"
  → router: agent
  → agent 노드: tool_call(manage_permission, {instruction: "내 접근 권한 알려줘"})
  → tool_gate: PermissionAgent.plan() → "query alice", RISK_SELECT → ALLOW (자동)
  → PermissionAgent.execute() → FGA 3회 조회 → 포맷된 스냅샷
  → agent_answer

관리자: "bob 접근 가능한 폴더 보여줘"
  → tool_gate: PermissionAgent.plan()
      → target_user_id="bob", caller="admin_user"
      → fga.check(admin_user, "member", "capability:admin") → True
      → "query bob", RISK_SELECT → ALLOW
  → execute() → bob 기준 FGA 조회
```

## 영향받지 않는 것

- 도구 외부 이름(`manage_permission`)은 변경 없음 — LLM에 노출되는 이름은 역할 기반(ADR-0033)
- `ToolRegistry` dataclass 구조 불변
- `tool_gate_node`의 `__caller_id` 주입 방식 불변
- `grant | revoke` 경로 로직 불변

## 테스트 계획

1. `test_permission_tool.py` → `test_permission_agent.py` 개명, import 수정
2. 신규 케이스:
   - `query` 본인 → `RISK_SELECT` 반환, FGA 3메서드 호출 확인
   - `query` 타인 + 관리자 → `RISK_SELECT`
   - `query` 타인 + 일반 유저 → `RISK_DENY`
3. `test_base.py`: `ToolAgent` Protocol import 수정
4. `test_sql_tool.py`, `test_audit_history_tool.py`: import 수정만

## ADR

본 설계 적용 후 ADR-0041 작성 예정.
