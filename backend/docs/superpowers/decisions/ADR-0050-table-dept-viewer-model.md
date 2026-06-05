# ADR-0050: type table dept_viewer 단일 relation 모델

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: ADR-0047에서 정의된 `type table`의 `can_access` relation을 `dept_viewer` 단일 relation으로 대체해, 폴더 권한 모델(ADR-0015, `folder.dept_viewer`)과 동형화한다. FGA 모델의 일관성 강화와 `manage_permission` 도구의 파싱·검증 로직 재사용을 목표로 한다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. `can_access` 유지 (flat relation) | ADR-0047의 결정을 그대로 유지. 단순하지만 폴더와 이질적. `manage_permission` 파싱이 폴더(`dept_viewer`)와 테이블(`can_access`)을 별도 처리(코드 중복). |
| B. `dept_viewer` 단일 relation으로 대체 | 폴더·테이블 권한 모델 동형화. `manage_permission` 파싱·검증 로직 재사용. `gate_table_access()`는 relation 이름 한 줄만 변경. grant/revoke 인터페이스 통일. **채택** |

## Decision
**선택: B — `dept_viewer` 단일 relation으로 대체**

### FGA 모델 변경
```
type table
  relations
    define dept_viewer: [department#member]
    define can_read: dept_viewer or super_reader from parent
```

(ADR-0047의 `define can_access: [user, department#member, role#member]`를 폐기)

**핵심**:
- `dept_viewer`는 개별 부서 멤버만 허용(`[department#member]`). 개인 사용자(`[user]`) 직접 부여는 불가(폴더 모델과 대칭).
- `can_read`는 `dept_viewer` union 또는 상속된 `super_reader`로 판정. (폴더의 `dept_access`와 동일 패턴)
- 테이블도 단일 루트 parent를 가질 수 있으나, 현 설계(DB 스키마 고정, `_KNOWN_TABLES` 코드 상수)에선 테이블은 독립(parent 없음)이므로 직접 `dept_viewer` 부여만 필요.

### 시드 변경
`scripts/seed_fga.py`의 `_TABLE_GRANTS`:
- 기존 `table:X` → `check(user, can_access, table:X)`를 `check(user, dept_viewer, table:X)`로 변경.
- grant 인터페이스 동일: `add_relation("table:name", "dept_viewer", "department:deptid#member")`.

### 게이트 함수 변경
`core/sql/gate.py`의 `gate_table_access()`:
```python
# Before
result = check(user_id, "can_access", f"table:{table_name}")

# After
result = check(user_id, "dept_viewer", f"table:{table_name}")
```

### manage_permission 도구 통일
`app/tools/manage_permission.py`의 `_parse_permission()` 함수가 이미 폴더와 테이블을 구분(`"table:"` prefix)해 처리한다. relation 이름을 "폴더면 `dept_viewer`, 테이블도 `dept_viewer`"로 통일하면, 파싱 로직에서 한 가지 relation만 처리하게 된다.

## Rationale

- **모델 동형성**: 폴더(`ADR-0015`)와 테이블(`ADR-0050`)이 모두 `dept_viewer` relation을 사용하므로, 사용자 입장에서 "부서 멤버가 폴더/테이블을 열람한다"는 개념이 일관성 있게 표현된다. 정책 설명과 구현이 1:1 대응.

- **코드 재사용**: `manage_permission` 도구가 이미 폴더·테이블을 prefix로 구분한다. relation 이름을 통일하면, 파싱·검증·grant/revoke 로직을 한 번만 구현해 둘 다에 적용할 수 있다. 코드 중복 제거.

- **fail-closed 안전성**: `dept_viewer` 튜플이 없는 테이블은 DENY가 기본값이라, 새 테이블 추가 시 시드를 빠뜨리면 열리는 게 아니라 닫히는 방향이다(ADR-0047 rationale 재사용).

- **super_reader 예약**: 테이블은 현재 parent 없으나, 향후 테이블 계층화(예: `table:business`, `table:business#sales`)가 필요하면 `super_reader` 상속도 손쉽게 추가할 수 있게 reservation을 미리 정의해둔다.

## 관련
- [ADR-0047](ADR-0047-table-level-sql-access.md) — `can_access` 원래 정의 (본 ADR이 supersede)
- [ADR-0015](ADR-0015-fga-public-private-super-reader.md) — 폴더 `dept_viewer` 모델 (동형 대상)
- [ADR-0028](ADR-0028-capability-permission-model.md) — SQL 위험도 capability 게이트 (테이블 게이트와 AND 결합)
