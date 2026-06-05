# ADR-0046: 개인 권한 부여/회수 + 부서 관리자 위임

> **Status**: 🟣 대체됨 → [ADR-0051](ADR-0051-permission-node-separation.md)

> ⚠️ 위임 단위가 멤버십→permission 배정으로 재설계됨(ADR-0051). 본 ADR의 "멤버십만 위임" 결정은 "정의(c_level)/배정(c_level+팀장)" 분리 모델로 대체됨.

**Date**: 2026-06-05
**Context**: `manage_permission`(ADR-0029)은 grant/revoke 도구는 갖췄으나 권한을 부여·회수할 수 있는 주체가 전역 관리자(`role:c_level#member` → `capability:admin#justify_grant`) 하나뿐이라, 팀장이 자기 부서원을 직접 관리하는 위임이 불가능하다. 다른 멤버에게 실제로 부여/회수할 수 있도록 **부서 관리자(dept admin) 위임**을 추가하고, revoke 종단 동작을 검증한다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 부서 관리자(dept admin) — `department.admin` | 관리 단위가 부서라 현 모델(department 중심)과 정합. 위임 경계가 명확(자기 부서). **채택** |
| B. 폴더 소유자(folder owner) | 폴더 단위 위임은 유연하나 폴더 소유 모델을 새로 도입해야 함. 현 범위 초과 |
| C. capability 범위 스코프 | 가장 일반적이나 grant 메타권한을 객체별로 쪼개야 해 복잡. YAGNI |

### 위임 범위(B 하위 결정)
| 선택지 | 트레이드오프 |
|--------|------------|
| 멤버십만 위임 | 부서 admin이 자기 부서 `member` 추가/제거만. 경계 넘는 누수 없음. **채택** |
| 멤버십 + `dept_viewer` | dept admin이 임의 폴더에 자기 부서를 끼워넣어 **부서 경계를 넘는 폴더 누수** 발생(예: 타 부서 private 폴더). 폴더측 권한을 묶을 모델이 없어 안전 차단 불가 → 기각 |

## Decision
**선택: A(부서 관리자) + "멤버십만 위임"**

1. **모델**: `fga/model.fga`의 `department`에 `define admin: [user]` 추가(+`model.json` 동기). `user:X → admin → department:Y`.
2. **게이트 위임(멤버십 한정)**: 권한 도구의 planned_action이 `grant|revoke <user> member department:Y` 형태이고, 게이트(`gate_decision`, RISK_GRANT)가 전역 관리자 부재로 DENY를 낼 때, 요청자가 `admin @ department:Y`이면 **JUSTIFY_AND_APPROVE로 승격**(사유 기재 후 실행). 전역 c_level은 기존대로 모든 grant를 JUSTIFY로 수행.
3. **경계 불변식**: `dept_viewer`(폴더 부서 접근권)·`capability` 부여는 **전역 c_level 전용** 유지. 부서 admin은 폴더·전사 권한을 위임할 수 없다(권한 상승 차단).
4. **개인 단위 SQL capability**: 이미 `PermissionValidator`가 `user:<id>` 주체에 capability 부여를 허용하므로(개인 직접 부여 가능) 모델 변경 없음 — 본 ADR은 이를 지원 사실로 확인하고, 폴더 개인 접근권(`individual_viewer`)은 **비목표**로 명시 제외(부서 단위 모델 유지, [[project_access_control]]).
5. **revoke 종단 검증**: grant→check(true)→revoke→check(false) 왕복과 캐시 즉시 무효화(`_cache_key_for`, ADR-0029 회귀 방지)를 테스트로 고정.

### 게이트 합성 위치
`gate_decision`(core.sql.gate)은 위험도만 보는 순수 함수로 유지한다. 대상 부서에 의존하는 위임 판정은 도구 의미(planned_action 포맷)를 아는 `tool_gate_node`(app 레이어)가 `gate_decision` 결과 위에 합성한다 — core는 도구 불가지 유지.

## Rationale
- **부서 관리자 모델**: 부서 멤버십이 이미 OpenFGA의 1급 개념(`department#member`)이고 멤버십 추가/제거가 가장 빈번한 위임 작업이므로, 관리 단위를 부서로 두는 것이 현 아키텍처와 가장 적은 마찰로 결합한다.
- **멤버십만 위임**: `dept_viewer` 위임은 `department:Y#member → dept_viewer → folder:Z`라 부서 admin이 **임의 폴더 Z**에 자기 부서를 끼워넣을 수 있어 부서 경계를 넘는 누수가 된다. 이를 안전하게 막으려면 "폴더 Z에 대한 권한"을 dept admin 쪽에 묶어야 하는데 그 모델(폴더 소유자)은 본 범위 밖이다. 따라서 누수 위험이 없는 멤버십 위임으로 한정하고, 폴더·전사 권한 위임은 전역 관리자에 남긴다.
- **JUSTIFY로 통일**: 전역 grant가 사유 기재(JUSTIFY_AND_APPROVE)인 것과 동일하게, 부서 admin 위임도 무조건 사유를 남기게 해 감사 이력(ADR-0018)을 일관 유지한다.

## 관련
- [[project_access_control]] — OpenFGA department/folder 모델
- [ADR-0029](ADR-0029-permission-management-tool.md) — manage_permission 본체("차등 위임"을 후속으로 남긴 항목을 본 ADR이 해소)
- [ADR-0028](ADR-0028-capability-permission-model.md) — capability 게이트 모델
- [ADR-0047](ADR-0047-table-level-sql-access.md) — 같은 PR의 테이블별 SQL 접근 권한
