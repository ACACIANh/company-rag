# 테이블 권한 관리 설계

**Date**: 2026-06-05

## 배경

ADR-0047에서 `type table` FGA 모델과 `gate_table_access()` 게이트가 정의됐지만,
`manage_permission` 도구를 통한 런타임 grant/revoke와 권한 스냅샷 노출이 구현되지 않았다.
또한 기존 모델(`can_access: [user, department#member, role#member]`)이 단순하지만
폴더의 `dept_viewer` 패턴과 달라 관리 인터페이스가 이질적이었다.

## 결정

### 핵심 설계 결정

- **FGA 모델**: `can_access` 제거, `dept_viewer: [user, department#member, role#member]` 단일 relation으로 통일
- **테이블 목록 관리**: 코드 상수 (`_KNOWN_TABLES`) — DB 스키마가 고정된 프로젝트에 얹는 구조이므로 yaml 불필요
- **grant 주체**: user·department#member·role#member 모두 허용 (`dept_viewer` 단일 relation)
- **gate 체크**: `gate_table_access()`가 `dept_viewer`를 체크 (기존 `can_access` 대체)

### 폴더와의 대칭

| | 폴더 | 테이블 |
|--|------|--------|
| grant relation | `dept_viewer` | `dept_viewer` |
| 최종 권한 | `can_read` (계산) | `dept_viewer` (직접 체크) |
| 부서 단위 | `department:X#member` | `department:X#member` |
| 개인 단위 | ❌ (folder 모델 미지원) | ✅ `user:alice` |
| 역할 단위 | `role:X#member` (super_reader 경유) | `role:X#member` |

테이블은 계층 구조(parent/상속)가 없으므로 `can_read` 같은 계산 relation 불필요.
`dept_viewer` 하나로 충분.

## 변경 파일

### 1. `fga/model.fga`

```
type table
  relations
    define dept_viewer: [user, department#member, role#member]
```

`can_access` 완전 제거.

### 2. `scripts/seed_fga.py`

`_TABLE_GRANTS` relation `can_access` → `dept_viewer` 전환:

```python
_TABLE_GRANTS = [
    {"user": "role:c_level#member",        "relation": "dept_viewer", "object": "table:employees"},
    {"user": "role:c_level#member",        "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:인사팀#member",   "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:재무팀#member",   "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:재무팀#member",   "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:개발팀#member",   "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:개발팀#member",   "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:영업팀#member",   "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:제품팀#member",   "relation": "dept_viewer", "object": "table:sales"},
]
```

### 3. `core/sql/gate.py`

`gate_table_access()` 체크 relation 변경:
```python
# 변경 전
if not await check(user, "can_access", f"table:{table}"):
# 변경 후
if not await check(user, "dept_viewer", f"table:{table}"):
```

### 4. `core/fga/permission_validator.py`

`_KNOWN_TABLES` 상수 추가:
```python
_KNOWN_TABLES = {"employees", "sales"}
```

`validate()`에 `dept_viewer on table:*` 케이스 추가:
```python
elif relation == "dept_viewer" and object_.startswith("table:"):
    table = self._strip(object_, "table:")
    if table not in _KNOWN_TABLES:
        return None
    resolved = self._resolve_user(subject)
    if resolved is not None:
        subject = resolved
    else:
        dept = self._strip(subject, "department:")
        if dept is not None and dept.endswith("#member"):
            dept = dept[:-len("#member")]
        else:
            # role#member 직접 grant (c_level 시드 전용, NL 파싱에서는 미노출)
            role = self._strip(subject, "role:")
            if role is not None and role.endswith("#member"):
                pass  # 허용
            else:
                return None
        if dept is not None and dept not in self._departments:
            return None
```

`catalog_text()`에 테이블 목록 추가:
```python
tables = ", ".join(sorted(_KNOWN_TABLES))
return f"유저: {users}\n부서: {depts}\n폴더: {folders}\n테이블: {tables}"
```

### 5. `core/fga/client.py`

`user_accessible_tables()` 메서드 추가:
```python
async def user_accessible_tables(self, user_id: str) -> list[str]:
    from core.fga.permission_validator import _KNOWN_TABLES
    result = []
    for table in sorted(_KNOWN_TABLES):
        if await self.check(f"user:{user_id}", "dept_viewer", f"table:{table}"):
            result.append(table)
    return result
```

### 6. `app/graph/tools/permission_tool.py`

`execute()`의 query 분기에서 `user_accessible_tables()` 호출 추가.
`_format_permission_snapshot()`에 테이블 섹션 추가:
```
접근 가능 테이블: employees, sales
```

## 테스트

### `tests/core/sql/test_gate.py` 확장
- `dept_viewer` 보유 → PASS
- `dept_viewer` 미보유 → DENY
- 미지 테이블 → fail-closed DENY (빈 집합 → 통과 기존 동작 유지)

### `tests/core/fga/test_permission_validator.py` 확장
- `department:인사팀#member dept_viewer table:employees` → valid
- `user:alice dept_viewer table:sales` → valid
- `user:alice dept_viewer table:unknown_table` → None
- `user:alice can_access table:employees` → None (can_access는 더 이상 grant 대상 아님)

### `tests/app/graph/nodes/test_tool_gate.py` 확장
- 위험도 ALLOW + `dept_viewer` 보유 → 통과
- 위험도 ALLOW + `dept_viewer` 미보유 → DENY

## 마이그레이션 노트

기존 `can_access` 튜플이 FGA store에 살아 있으면 stale이 됨.
`python -m scripts.seed_fga --prune` 실행으로 정합화 필요.
