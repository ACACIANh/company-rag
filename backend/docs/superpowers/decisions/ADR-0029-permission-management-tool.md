# ADR-0029: 권한 관리 도구 manage_permission (SP2b)

> **Status**: ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: SP2a(ADR-0028)로 SQL 게이트가 OpenFGA capability 모델로 통일되어, 게이트 정책이 코드가 아니라 튜플(데이터)로 운영된다. 이제 그 권한 튜플을 **에이전트 도구로 조작**한다(SP2b). tool_call 에이전트 루프(ADR-0023)에 `manage_permission` 도구를 등록해, 권한자가 자연어로 권한을 부여/회수하고, 그 행위 자체가 capability 게이트(메타권한)·HITL·감사를 거치게 한다.

## Options

### 결정 1 — grant/revoke 대상 권한
| 선택지 | 채택 |
|--------|------|
| 부서 멤버십(user↔department) | ✅ |
| 폴더 부서 접근권(department↔folder, dept_viewer) | ✅ |
| SQL capability(user·department↔capability:sql relation) | ✅ |
| 역할 멤버십(user↔role, c_level 등) | ❌ 최고위험 — SP2b 제외 |

### 결정 2 — 메타권한(누가 grant 가능)
| 선택지 | 트레이드오프 |
|--------|------------|
| **capability:admin 모델 확장** | SP2a 철학 계승 — "부여하는 권한"도 부여 가능한 capability. gate_decision이 권한쓰기 risk도 판정. 고위험이라 JUSTIFY(사유 기재) |
| 별도 owner/admin 관계 | ReBAC 위임("부서장이 자기 부서") 표현력 ↑, 모델·게이트 복잡도 ↑ |
| 고정 정책(c_level만, 코드) | 단순하나 "게이트=데이터" 철학과 어긋남, 재배포로만 변경 |

### 결정 3 — grant 권한 세분화
| 선택지 | 트레이드오프 |
|--------|------------|
| **단일 grant 권한**(allow_grant/justify_grant) | grant 권한 보유 시 3종 모두 부여 가능. 단순·YAGNI |
| 권한타입별(grant_department/folder/capability) | 차등 위임 가능, relation 6개·복잡 |

### 결정 4 — 도구 입력 형식
| 선택지 | 트레이드오프 |
|--------|------------|
| **NL 입력 + plan에서 구조화+검증** | 사용자엔 자연어, 내부는 구조화. SQL 도구(NL→SQL→AST검증)와 동형. LLM 파싱 결과를 화이트리스트로 검증해 환각·주입 차단 |
| 구조화 인자(bind_tools schema) | 검증 명확하나 SQL 도구와 비일관 |

## Decision

**결정 1: 부서 멤버십 + 폴더 부서 접근권 + SQL capability (역할 멤버십 제외).**
**결정 2: capability:admin 모델 확장 (JUSTIFY 게이트).**
**결정 3: 단일 grant 권한.**
**결정 4: NL 입력 + plan에서 구조화+검증.**

### 구현 범위 (SP2b)

#### ① 도구 — `app/graph/tools/permission_tool.py`
`manage_permission(instruction: str)` — NL 단일 인자. registry(`build_tool_registry`)에 `fga_client` 주입해 등록.

`plan(args) -> (planned_action, risk)`:
1. LLM이 `instruction` → 구조화 파싱 (`relation`이 권한 타입을 결정 — `member`=부서멤버십 / `dept_viewer`=폴더접근권 / `allow_*`·`justify_*`=capability):
   ```
   {action: grant|revoke, subject, relation, object}
   ```
2. **검증**(화이트리스트, 미통과 → `risk=RISK_DENY`):
   - `target_type`별 subject/object 타입 정합
   - subject·object id 유효성 (부서·유저 `users.yaml`, 폴더 `folders.yaml`, capability relation 고정 8종). "이미 그 상태인가"는 멱등이라 불검증.
3. `planned_action` = 사람이 읽는 동작 문자열(예: `"grant: user:alice → member → department:engineering"`), `risk` = `RISK_GRANT`(고정 고위험).

`execute(planned_action)`: 검증된 구조를 튜플로 변환해 FGA write/delete → 결과 텍스트.

| target_type | subject | relation | object |
|---|---|---|---|
| department_member | `user:X` | `member` | `department:Y` |
| folder_viewer | `department:X#member` | `dept_viewer` | `folder:Y` |
| capability | `user:X` 또는 `department:X#member` | `allow_select`…(8종) | `capability:sql` |

#### ② 위험도·게이트 — `core/sql/gate.py`
`RISK_GRANT` 추가. `gate_decision`을 risk별 `(객체, relation 베이스)` 매핑으로 일반화:
```python
_RISK_GATE = {
    RISK_SELECT:        ("capability:sql",   "select"),
    RISK_BULK_SELECT:   ("capability:sql",   "bulk_select"),
    RISK_UPDATE_DELETE: ("capability:sql",   "update_delete"),
    RISK_DDL:           ("capability:sql",   "ddl"),
    RISK_GRANT:         ("capability:admin", "grant"),
}
# allow_<base>@<obj> → ALLOW, justify_<base>@<obj> → JUSTIFY, 둘 다 없으면 DENY
```
capability:admin도 SP2a와 동일한 2층 구조라 게이트 로직 불변, 매핑만 추가.

#### ③ 모델 — `fga/model.fga`
`capability` 타입에 `allow_grant`/`justify_grant` 2 relation 추가(`[user, department#member, role#member]`). `capability:admin` 인스턴스가 사용.

#### ④ FGAClient — `core/fga/client.py`
범용 쓰기 메서드:
```python
async def grant_tuple(self, subject, relation, object_) -> None    # write + 캐시 무효화
async def revoke_tuple(self, subject, relation, object_) -> None   # delete + 캐시 무효화
```
멱등(`_is_idempotent_fga_error` 재사용). `department_member` 변경은 해당 user 캐시 즉시 무효화, `folder_viewer`/`capability`는 TTL 만료 의존(전체 무효화는 과복잡 — YAGNI).

#### ⑤ 검증기 — `core/fga/`
화이트리스트 검증기(LangGraph 불가지). `users.yaml`/`folders.yaml`/고정 capability relation을 도구 init 시 1회 로드.

#### ⑥ 시드 — `scripts/seed_fga.py`
`_CAPABILITY_GRANTS`에 추가: `role:c_level#member` → `justify_grant` → `capability:admin`. (`allow_grant`는 비움 — grant는 항상 사유 기재.)

#### ⑦ HITL — 무변경
grant가 JUSTIFY로 떨어지면 SP1(ADR-0023/0024)의 `tool_gate → confirm(계획 노출) → justify_execute` 흐름이 도구 불가지라 그대로 작동. confirm이 grant 동작을 노출하고, 사유 입력 후 justify_execute가 `execute` 호출. 추가 노드 0개.

## Rationale

- **결정 2(capability:admin)**: SP2a가 "게이트를 코드가 아니라 데이터로" 만든 동기를 grant 권한까지 일관 적용. 권한을 부여하는 권한도 동일한 capability 2층 모델 위에 둬, gate_decision 한 군데 매핑 추가로 통합된다. 별도 owner/admin 관계(ReBAC 위임)는 표현력이 크지만 지금 차등 위임 요구가 없어 YAGNI.
- **결정 3(단일 grant)**: 권한 종류가 적고 차등 위임 수요가 아직 없다. 단일로 시작하고 필요 시 세분화.
- **결정 4(NL+검증)**: SQL 도구와 동형으로 일관되며, 사용자에겐 자연어가 자연스럽다. 핵심은 LLM 파싱 결과를 그대로 튜플로 쓰지 않고 화이트리스트로 검증하는 것 — SQL이 AST 검증을 거치듯 권한은 스키마 검증을 거쳐 환각·주입을 차단한다.
- **JUSTIFY 기본**: grant는 비가역적 권한 변경이라 ADR-0027 철학(고위험일수록 기록)에 따라 사유 기재를 강제한다. allow_grant를 비워 c_level도 사유를 남긴다.

## Consequences

- `gate_decision` 시그니처는 불변(risk만 추가). SP2a 게이트 테스트는 RISK_GRANT 케이스만 확장.
- capability 타입이 sql relation(8) + grant relation(2)을 함께 정의 — 인스턴스(`capability:sql`/`capability:admin`)로 용도 구분.
- 권한 변경 즉시성: `folder_viewer`/`capability` grant는 FGA 캐시 TTL만큼 지연 반영(즉시 필요 시 후속 과제).
- 감사: grant/revoke도 기존 `AuditRecord`로 기록(generated_sql 필드에 planned_action, reason에 사유).
- **SP2b 제외**: 역할 멤버십(c_level 부여), 차등 위임, folder_viewer 캐시 즉시 무효화 — 필요 시 후속.

## DoD
1. `permission_tool` plan(파싱·검증)·execute 단위 테스트(유효/무효/멱등).
2. `gate_decision` RISK_GRANT 케이스 테스트(capability:admin allow/justify/deny).
3. `grant_tuple`/`revoke_tuple` 단위 테스트.
4. 통합: `manage_permission` 등록 + tool_call 경로 grant → JUSTIFY → confirm → execute, 실제 FGA 튜플 반영 확인.
5. eval 회귀(영향 없음 예상 — 게이트 추가는 기존 SQL 경로 불변).
6. ADR 인덱스 재생성.

## 관련 ADR
- [[ADR-0028]] capability 권한 모델(SP2a) — 이 도구가 조작하는 튜플·게이트 기반
- [[ADR-0023]] tool_call 에이전트 루프 — manage_permission이 등록되는 골격
- [[ADR-0024]] HITL API resume — grant JUSTIFY가 재사용하는 confirm/resume
- [[ADR-0027]] JUSTIFY_AND_APPROVE self-service 게이트 — grant 사유 기재 근거
