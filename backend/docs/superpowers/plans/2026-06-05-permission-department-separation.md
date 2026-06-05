# 권한↔부서 분리 (permission 1급 노드) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 권한 부여를 부서 멤버십에서 분리 — `permission` 노드를 도입해 부서 가입 없이 폴더·테이블·SQL 묶음을 개인에게 직접 부여 가능하게 한다.

**Architecture:** OpenFGA 모델에 `type permission`을 신설하고, 기존 `department#member` 직접 주입을 `permission#holder` 경유(TTU)로 전환한다. folder/table의 `dept_viewer`→`viewer` 개명, capability를 `permission#holder`로 통일. 부서 id에서 "팀"을 제거(`인사팀`→`인사`)해 permission 이름과 일치시킨다. 검색/실행 코드는 불변 — FGA가 `user → permission#holder → gated_by → folder/table`를 내부 해소한다.

**Tech Stack:** OpenFGA (model.fga DSL + model.json), Python 3.11 (`.venv/bin/python`), pytest, asyncpg, LangGraph.

**Spec:** `docs/superpowers/specs/2026-06-05-permission-department-separation-design.md`

**실행 규칙:** 모든 명령은 `backend/` cwd 기준. 인터프리터는 `.venv/bin/python`(시스템 `python` 없음). 브랜치는 이미 `feat/permission-department-separation`. 테스트는 FGA 서버 없이 도는 순수 단위 테스트(`_build_tuples`·`PermissionValidator` 직접 호출, mock) — 통합 스모크는 Task 8에서만 실제 OpenFGA를 띄운다.

---

## File Structure

**신설:**
- `config/permissions.yaml` — permission 정의 SSOT(묶음별 holders/folders/tables/sql). 부서·폴더·테이블 매핑의 단일 출처.

**수정:**
- `fga/model.fga` + `fga/model.json` — `type permission` 신설, folder/table `dept_viewer`→`viewer`(TTU)·`gated_by` 신설, capability를 `permission#holder`로
- `config/users.yaml`, `config/folders.yaml` — 부서 id 정규화(팀 제거)
- `scripts/seed_fga.py` — permission 경유 튜플 생성(`_build_tuples`, `_CAPABILITY_GRANTS`/`_TABLE_GRANTS` 폐지→permissions.yaml)
- `core/fga/permission_validator.py` — `holder`(배정)·`gated_by`(정의) 화이트리스트, `viewer` 개명, 부서명 정규화
- `app/graph/prompts.py` — `PERMISSION_PARSE_PROMPT` NL 파싱 규칙(유저→부서 번역 폐기→permission holder)
- `core/fga/client.py`, `core/sql/gate.py` — `dept_viewer`→`viewer` 개명, permission 위임 판정 헬퍼
- `app/graph/tools/permission_tool.py`, `app/graph/nodes/tool_gate.py` — permission 배정 위임 승격
- 대응 테스트: `tests/scripts/test_seed_fga.py`, `tests/core/fga/test_permission_validator.py`, `tests/core/sql/test_gate.py`, `tests/app/graph/tools/test_permission_tool.py`, `tests/app/graph/nodes/test_tool_gate.py`, `tests/core/fga/test_client.py`
- ADR: `ADR-0051`(신규) + `ADR-0046`/`0015`/`0050` 상태·본문 갱신

**부서 7개**(정규화 후): `개발 인사 제품 디자인 영업 재무 법무`. 디자인은 공개 폴더만 보므로 전용 permission이 없다(전직원 `permission:기본` + 공개 폴더로 충분).

---

## Task 1: config 레이어 — 부서 id 정규화 + permissions.yaml

**Files:**
- Modify: `config/users.yaml`, `config/folders.yaml`
- Create: `config/permissions.yaml`

- [ ] **Step 1: `config/users.yaml` 부서명에서 "팀" 제거**

`departments`와 `dept_admin_of` 값에서 `개발팀→개발`, `인사팀→인사`, `제품팀→제품`, `디자인팀→디자인`, `영업팀→영업`, `재무팀→재무`, `법무팀→법무`로 치환. 예시(joohwan·mido·chaewon·taeyang은 다중/admin):

```yaml
  - username: joohwan
    # ...
    departments: [개발]
    dept_admin_of: [개발]   # 부서 관리자 — 개발 멤버십 위임 (ADR-0046→0051)
  - username: minjun
    departments: [인사]
  - username: mido
    departments: [개발, 제품]
  - username: chaewon
    departments: [영업, 재무]
  - username: taeyang
    departments: [인사, 법무]
```

sed 일괄(검토 후): `sed -i '' -E 's/(개발|인사|제품|디자인|영업|재무|법무)팀/\1/g' config/users.yaml config/folders.yaml`

- [ ] **Step 2: `config/folders.yaml` — `dept_viewers` 제거(권한은 permissions.yaml로 이관)**

명시 권한은 이제 permissions.yaml이 담당하므로 `dept_viewers` 키를 모두 제거하고 `private: true` 표식만 남긴다. `/company`의 `public: true`·`super_readers: [c_level]`는 유지(폴더 전사열람은 role 경유). 결과:

```yaml
  /company/engineering/ops:
    private: true              # 배포·인시던트 — 공개 차단, permission:개발이 gate
  /company/hr:
    private: true              # permission:인사가 gate
  /company/finance:
    private: true              # permission:재무가 gate
  /company/legal:
    private: true              # permission:법무가 gate
```

- [ ] **Step 3: `config/permissions.yaml` 신설**

```yaml
# permission 정의 SSOT (ADR-0051). 이름은 부서 id와 통일(permission:인사 = department:인사).
# holders: 이 권한을 기본 보유하는 주체(부서·역할·전직원). 개인 배정은 런타임(manage_permission).
# folders/tables: 이 권한이 여는 접근대상. sql: 묶이는 capability:sql relation.
permissions:
  기본:                      # 전 직원 — 기본 SELECT/대량SELECT
    holders: ["user:*"]
    sql: [allow_select, justify_bulk_select]
  인사:
    holders: ["department:인사#member"]
    folders: [/company/hr]
    tables:  [employees]
  재무:
    holders: ["department:재무#member"]
    folders: [/company/finance]
    tables:  [employees, sales]
  개발:
    holders: ["department:개발#member"]
    folders: [/company/engineering/ops]
    tables:  [employees, sales, equipment]
    sql:     [justify_update_delete]
  영업:
    holders: ["department:영업#member"]
    tables:  [sales]
  제품:
    holders: ["department:제품#member"]
    tables:  [sales]
  법무:
    holders: ["department:법무#member"]
    folders: [/company/legal]
  전사:                      # c_level — 테이블·SQL만(폴더 전사열람은 super_reader 유지)
    holders: ["role:c_level#member"]
    tables:  [employees, sales, equipment]
    sql:     [justify_update_delete]
```

- [ ] **Step 4: yaml 파싱·정합 검증**

Run:
```bash
.venv/bin/python -c "
import yaml
u = yaml.safe_load(open('config/users.yaml'))['users']
f = yaml.safe_load(open('config/folders.yaml'))['folders']
p = yaml.safe_load(open('config/permissions.yaml'))['permissions']
depts = {d for usr in u for d in usr.get('departments', [])}
assert not any('팀' in d for d in depts), f'팀 잔재: {depts}'
print('부서:', sorted(depts))
print('permissions:', sorted(p))
# permissions.yaml의 folders가 모두 folders.yaml에 존재하는지 + dept_viewers 잔재 없음
pf = {path for s in p.values() if s for path in (s or {}).get('folders', [])}
assert pf <= set(f), f'folders.yaml 누락: {pf - set(f)}'
assert not any((s or {}).get('dept_viewers') for s in f.values()), 'folders.yaml dept_viewers 잔재'
print('OK')
"
```
Expected: `팀` 잔재 없음, `부서: ['개발','디자인','법무','영업','인사','재무','제품']`, `OK`.

- [ ] **Step 5: Commit**

```bash
git add config/users.yaml config/folders.yaml config/permissions.yaml
git commit -m "feat(config): 부서 id 정규화(팀 제거) + permissions.yaml 신설 (ADR-0051)"
```

---

## Task 2: FGA 모델 — `type permission` + viewer 개명 + capability permission화

**Files:**
- Modify: `fga/model.fga` (DSL, 사람이 읽는 SSOT), `fga/model.json` (fga_init.sh가 업로드하는 실제본 — 1:1 동기화)

> fga CLI가 없으므로 두 파일을 수동 동기화한다. 아래는 **완성본 전체**다(그대로 교체).

- [ ] **Step 1: `fga/model.fga` 전체 교체**

```
model
  schema 1.1

type user

type role
  relations
    define member: [user]          # c_level 같은 전사 역할

type department
  relations
    define member: [user]
    define admin: [user]           # 부서 관리자 — 자기 부서 멤버십·permission 배정 위임 (ADR-0051)

# 권한 묶음(ADR-0051). holder = 이 권한을 가진 주체(개인·전직원·부서·역할).
# folder/table/capability가 gated_by/holder로 이 노드를 경유해 권한 주체를 부서에서 분리한다.
type permission
  relations
    define holder: [user, user:*, department#member, role#member]

type folder
  relations
    define parent: [folder]

    # 명시 권한 — permission 경유(구 dept_viewer). holder from gated_by(TTU).
    define gated_by: [permission]
    define viewer: holder from gated_by
    define access: viewer or access from parent

    # 전 직원 공개 (루트 user:* → 상속)
    define public_viewer: [user:*]
    define public_access: public_viewer or public_access from parent

    # private 표식 (이 서브트리는 공개 차단)
    define private_flag: [user:*] or private_flag from parent

    # 전사 상위 열람권 (private도 뚫음, 루트에 부여하면 서브트리 상속)
    define super_reader: [role#member] or super_reader from parent

    define can_read: super_reader or access or (public_access but not private_flag)

type capability
  relations
    # SQL 권한 — 전부 permission 경유(ADR-0051). 단순 SELECT만 allow_*(즉시),
    # 그 외 위험군은 justify_*(사유 기재). 주체는 permission#holder 단일.
    define allow_select:          [permission#holder]
    define justify_select:        [permission#holder]
    define justify_bulk_select:   [permission#holder]
    define justify_update_delete: [permission#holder]
    define justify_ddl:           [permission#holder]
    # 권한 관리(메타권한, ADR-0029)는 permission 비포함 — 역할·부서 직접.
    define justify_grant:         [user, department#member, role#member]

# 업무 DB 테이블 단위 접근권 (ADR-0050→0051). permission 경유로 폴더와 동형.
type table
  relations
    define gated_by: [permission]
    define viewer: holder from gated_by
```

- [ ] **Step 2: `fga/model.json` 전체 교체**

```json
{
  "schema_version": "1.1",
  "type_definitions": [
    { "type": "user" },
    {
      "type": "role",
      "relations": { "member": { "this": {} } },
      "metadata": { "relations": { "member": { "directly_related_user_types": [ { "type": "user" } ] } } }
    },
    {
      "type": "department",
      "relations": { "member": { "this": {} }, "admin": { "this": {} } },
      "metadata": { "relations": {
        "member": { "directly_related_user_types": [ { "type": "user" } ] },
        "admin": { "directly_related_user_types": [ { "type": "user" } ] }
      } }
    },
    {
      "type": "permission",
      "relations": { "holder": { "this": {} } },
      "metadata": { "relations": {
        "holder": { "directly_related_user_types": [
          { "type": "user" },
          { "type": "user", "wildcard": {} },
          { "type": "department", "relation": "member" },
          { "type": "role", "relation": "member" }
        ] }
      } }
    },
    {
      "type": "folder",
      "relations": {
        "parent": { "this": {} },
        "gated_by": { "this": {} },
        "viewer": {
          "tupleToUserset": {
            "tupleset": { "relation": "gated_by" },
            "computedUserset": { "relation": "holder" }
          }
        },
        "access": {
          "union": { "child": [
            { "computedUserset": { "relation": "viewer" } },
            { "tupleToUserset": { "tupleset": { "relation": "parent" }, "computedUserset": { "relation": "access" } } }
          ] }
        },
        "public_viewer": { "this": {} },
        "public_access": {
          "union": { "child": [
            { "computedUserset": { "relation": "public_viewer" } },
            { "tupleToUserset": { "tupleset": { "relation": "parent" }, "computedUserset": { "relation": "public_access" } } }
          ] }
        },
        "private_flag": {
          "union": { "child": [
            { "this": {} },
            { "tupleToUserset": { "tupleset": { "relation": "parent" }, "computedUserset": { "relation": "private_flag" } } }
          ] }
        },
        "super_reader": {
          "union": { "child": [
            { "this": {} },
            { "tupleToUserset": { "tupleset": { "relation": "parent" }, "computedUserset": { "relation": "super_reader" } } }
          ] }
        },
        "can_read": {
          "union": { "child": [
            { "computedUserset": { "relation": "super_reader" } },
            { "computedUserset": { "relation": "access" } },
            { "difference": {
              "base": { "computedUserset": { "relation": "public_access" } },
              "subtract": { "computedUserset": { "relation": "private_flag" } }
            } }
          ] }
        }
      },
      "metadata": { "relations": {
        "parent": { "directly_related_user_types": [ { "type": "folder" } ] },
        "gated_by": { "directly_related_user_types": [ { "type": "permission" } ] },
        "viewer": { "directly_related_user_types": [] },
        "access": { "directly_related_user_types": [] },
        "public_viewer": { "directly_related_user_types": [ { "type": "user", "wildcard": {} } ] },
        "public_access": { "directly_related_user_types": [] },
        "private_flag": { "directly_related_user_types": [ { "type": "user", "wildcard": {} } ] },
        "super_reader": { "directly_related_user_types": [ { "type": "role", "relation": "member" } ] },
        "can_read": { "directly_related_user_types": [] }
      } }
    },
    {
      "type": "capability",
      "relations": {
        "allow_select": { "this": {} },
        "justify_select": { "this": {} },
        "justify_bulk_select": { "this": {} },
        "justify_update_delete": { "this": {} },
        "justify_ddl": { "this": {} },
        "justify_grant": { "this": {} }
      },
      "metadata": { "relations": {
        "allow_select": { "directly_related_user_types": [ { "type": "permission", "relation": "holder" } ] },
        "justify_select": { "directly_related_user_types": [ { "type": "permission", "relation": "holder" } ] },
        "justify_bulk_select": { "directly_related_user_types": [ { "type": "permission", "relation": "holder" } ] },
        "justify_update_delete": { "directly_related_user_types": [ { "type": "permission", "relation": "holder" } ] },
        "justify_ddl": { "directly_related_user_types": [ { "type": "permission", "relation": "holder" } ] },
        "justify_grant": { "directly_related_user_types": [
          { "type": "user" },
          { "type": "department", "relation": "member" },
          { "type": "role", "relation": "member" }
        ] }
      } }
    },
    {
      "type": "table",
      "relations": {
        "gated_by": { "this": {} },
        "viewer": {
          "tupleToUserset": {
            "tupleset": { "relation": "gated_by" },
            "computedUserset": { "relation": "holder" }
          }
        }
      },
      "metadata": { "relations": {
        "gated_by": { "directly_related_user_types": [ { "type": "permission" } ] },
        "viewer": { "directly_related_user_types": [] }
      } }
    }
  ]
}
```

- [ ] **Step 3: JSON 유효성 + DSL↔JSON relation 정합 검증**

Run:
```bash
.venv/bin/python -c "
import json
m = json.load(open('fga/model.json'))
types = {t['type']: t for t in m['type_definitions']}
assert 'permission' in types, 'permission type 누락'
assert set(types['folder']['relations']) == {'parent','gated_by','viewer','access','public_viewer','public_access','private_flag','super_reader','can_read'}
assert set(types['table']['relations']) == {'gated_by','viewer'}
assert types['capability']['metadata']['relations']['allow_select']['directly_related_user_types'] == [{'type':'permission','relation':'holder'}]
print('model.json OK')
"
grep -c 'dept_viewer' fga/model.fga fga/model.json
```
Expected: `model.json OK`, 그리고 grep 결과 두 파일 모두 `:0`(dept_viewer 잔재 없음).

- [ ] **Step 4: Commit**

```bash
git add fga/model.fga fga/model.json
git commit -m "feat(fga): type permission 신설 + folder/table viewer(TTU) 개명 + capability permission화 (ADR-0051)"
```

---

## Task 3: `seed_fga.py` — permission 경유 튜플 생성

**Files:**
- Modify: `scripts/seed_fga.py`
- Test: `tests/scripts/test_seed_fga.py`

> `_CAPABILITY_GRANTS`·`_TABLE_GRANTS` 상수를 폐지하고, permission 묶음(holder/gated_by/capability)을 permissions.yaml에서 생성한다. `_build_tuples` 시그니처가 `(users, folders)` → `(users, folders, permissions)`로 바뀐다.

- [ ] **Step 1: 실패 테스트 작성** — `tests/scripts/test_seed_fga.py`의 테이블/폴더 dept_viewer 테스트를 permission 기반으로 교체하고 신규 추가

기존 테스트 중 **교체 대상**: `test_table_grants_present`, `test_table_grants_respect_boundary`, `test_dept_viewer_tuple`, `test_no_legacy_viewer_relation_emitted`, `test_finance_private_and_dept_viewer`, `test_legal_private_and_dept_viewer`. 그리고 모든 `_build_tuples(...)` 호출을 3-arg로(`_build_tuples(users, folders, permissions)`). 아래 블록으로 대체:

```python
# ── permission 묶음(ADR-0051) ──────────────────────────────
_PERMS = {
    "기본": {"holders": ["user:*"], "sql": ["allow_select", "justify_bulk_select"]},
    "인사": {"holders": ["department:인사#member"], "folders": ["/company/hr"], "tables": ["employees"]},
    "개발": {"holders": ["department:개발#member"], "folders": ["/company/engineering/ops"],
             "tables": ["employees", "sales", "equipment"], "sql": ["justify_update_delete"]},
    "전사": {"holders": ["role:c_level#member"], "tables": ["employees", "sales", "equipment"],
             "sql": ["justify_update_delete"]},
}


def test_permission_holder_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="department:인사#member", relation="holder", object="permission:인사")
    assert _find(tuples, user="user:*", relation="holder", object="permission:기본")
    assert _find(tuples, user="role:c_level#member", relation="holder", object="permission:전사")


def test_permission_folder_gated_by_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="permission:인사", relation="gated_by", object="folder:/company/hr")


def test_permission_table_gated_by_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="permission:인사", relation="gated_by", object="table:employees")
    assert _find(tuples, user="permission:개발", relation="gated_by", object="table:equipment")


def test_permission_capability_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    # 전직원 기본 SELECT는 permission:기본#holder 경유
    assert _find(tuples, user="permission:기본#holder", relation="allow_select", object="capability:sql")
    # 부서특화 UPDATE는 permission:개발#holder 경유
    assert _find(tuples, user="permission:개발#holder", relation="justify_update_delete", object="capability:sql")


def test_table_boundary_via_permission():
    # 영업은 employees(PII) 권한 없음 — permission:영업에 employees 미포함
    perms = {"영업": {"holders": ["department:영업#member"], "tables": ["sales"]}}
    tuples = _build_tuples([], {}, perms)
    assert _find(tuples, user="permission:영업", relation="gated_by", object="table:sales")
    assert not _find(tuples, user="permission:영업", relation="gated_by", object="table:employees")


def test_no_dept_viewer_relation_emitted():
    # 명시 권한은 permission#holder/gated_by로만 — dept_viewer 직접 튜플 없음
    tuples = _build_tuples([{"user_id": "user-x", "departments": ["인사"]}], {"/company/hr": {"private": True}}, _PERMS)
    assert not _find(tuples, relation="dept_viewer")
```

기존 유지 테스트(`test_department_membership_tuple` 등)의 `_build_tuples(...)` 호출에도 세 번째 인자 `{}`를 추가한다. `test_public_folder_tuple`/`test_private_folder_tuple`/`test_super_reader_tuple`/`test_parent_tuple_auto_derived`도 `_build_tuples([], {...}, {})`로.

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_fga.py -q`
Expected: FAIL — `_build_tuples() takes 2 positional arguments but 3 were given` (또는 permission 튜플 없음).

- [ ] **Step 3: `scripts/seed_fga.py` 구현**

(a) 상수 `_CAPABILITY_GRANTS`(L41-47)와 `_TABLE_GRANTS`(L53-65)를 **삭제**.

(b) `_build_tuples` 시그니처·본문 교체:

```python
def _build_tuples(users: list[dict], folders: dict, permissions: dict) -> list[dict]:
    tuples: list[dict] = []

    # 1) 멤버십(부서·역할·부서관리자) + admin JWT → capability:admin
    for user in users:
        uid = user["user_id"]
        for dept in user.get("departments", []):
            tuples.append({"user": f"user:{uid}", "relation": "member", "object": f"department:{dept}"})
        for role in user.get("fga_roles", []):
            tuples.append({"user": f"user:{uid}", "relation": "member", "object": f"role:{role}"})
        for dept in user.get("dept_admin_of", []):
            tuples.append({"user": f"user:{uid}", "relation": "admin", "object": f"department:{dept}"})
        if "admin" in user.get("roles", []):
            tuples.append({"user": f"user:{uid}", "relation": "justify_grant", "object": "capability:admin"})

    # 2) 폴더 구조(public/private/super_reader/parent) — 명시 권한은 permission이 담당(아래 3)
    for path, spec in folders.items():
        spec = spec or {}
        if spec.get("public"):
            tuples.append({"user": "user:*", "relation": "public_viewer", "object": f"folder:{path}"})
        if spec.get("private"):
            tuples.append({"user": "user:*", "relation": "private_flag", "object": f"folder:{path}"})
        for role in spec.get("super_readers", []):
            tuples.append({"user": f"role:{role}#member", "relation": "super_reader", "object": f"folder:{path}"})
        parent = _parent_of(path)
        if parent:
            tuples.append({"user": f"folder:{parent}", "relation": "parent", "object": f"folder:{path}"})

    # 3) permission 묶음(ADR-0051): holder 배정 + folder/table gated_by + capability#holder
    for name, pspec in permissions.items():
        pspec = pspec or {}
        perm = f"permission:{name}"
        for holder in pspec.get("holders", []):
            tuples.append({"user": holder, "relation": "holder", "object": perm})
        for path in pspec.get("folders", []):
            tuples.append({"user": perm, "relation": "gated_by", "object": f"folder:{path}"})
        for table in pspec.get("tables", []):
            tuples.append({"user": perm, "relation": "gated_by", "object": f"table:{table}"})
        for rel in pspec.get("sql", []):
            tuples.append({"user": f"{perm}#holder", "relation": rel, "object": "capability:sql"})

    return tuples
```

(c) `main()`에서 permissions.yaml 로드 + 호출 갱신(기존 L169-172 근처):

```python
    users = yaml.safe_load(Path("config/users.yaml").read_text())["users"]
    folders = yaml.safe_load(Path("config/folders.yaml").read_text())["folders"]
    permissions = yaml.safe_load(Path("config/permissions.yaml").read_text())["permissions"]

    tuples = _build_tuples(users, folders, permissions)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_fga.py -q`
Expected: PASS (전부).

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_fga.py tests/scripts/test_seed_fga.py
git commit -m "feat(seed): permission 경유 튜플 생성(holder/gated_by/capability) (ADR-0051)"
```

---

## Task 4: `permission_validator.py` — holder 배정 화이트리스트 + 개명

**Files:**
- Modify: `core/fga/permission_validator.py`
- Test: `tests/core/fga/test_permission_validator.py`

> manage_permission NL이 다루는 grant를 **`member`(부서 멤버십) + `holder`(permission 배정)** 두 가지로 정리한다. permission **정의**(gated_by/capability)는 NL이 아니라 permissions.yaml 재시드로 관리(c_level 운영)하므로 validator 대상이 아니다. 기존 `dept_viewer`(folder/table)·`_CAPABILITY_RELATIONS` 분기는 제거 — capability는 이제 permission#holder 경유라 직접 grant하지 않는다.

- [ ] **Step 1: 실패 테스트 작성** — folder/table `dept_viewer`·capability 분기 테스트를 `holder` 테스트로 교체

`tests/core/fga/test_permission_validator.py`에서 **삭제**: `test_valid_folder_viewer_grant`, `test_valid_capability_grant_to_department`, `test_reject_unknown_folder`, `test_reject_unknown_capability_relation`, `test_reject_removed_allow_capability_relations`, `test_validate_capability_grant_informal_user_subject`, 그리고 "테이블 dept_viewer 케이스" 블록 전체(`_table_validator`~`test_catalog_text_contains_table_names`). `_validator()`/`_resolver_validator()`에 `permissions` 인자 추가. 신규/대체:

```python
def _validator():
    return PermissionValidator(
        user_ids={"user-joohwan", "user-minjun"},
        departments={"개발", "영업"},
        permissions={"기본", "인사", "개발", "전사"},
    )


def test_valid_holder_grant_to_user():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "grant")


def test_valid_holder_grant_to_department():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:개발#member",
                      "relation": "holder", "object": "permission:개발"})
    assert tup == ("department:개발#member", "holder", "permission:개발", "grant")


def test_valid_holder_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "revoke")


def test_holder_informal_user_subject():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "grant")


def test_reject_holder_unknown_permission():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-minjun",
                       "relation": "holder", "object": "permission:secret"}) is None


def test_reject_holder_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "holder", "object": "permission:인사"}) is None


def test_reject_dept_viewer_relation_gone():
    # dept_viewer는 더 이상 grant 대상이 아님(permission 모델로 전환)
    v = _validator()
    assert v.validate({"action": "grant", "subject": "department:개발#member",
                       "relation": "dept_viewer", "object": "folder:/company/hr"}) is None


def test_catalog_text_contains_permissions():
    v = _validator()
    text = v.catalog_text()
    assert "인사" in text and "permission" in text.lower() or "권한" in text
```

`test_catalog_text_contains_known_ids`의 folder 단언(`"/company/finance" in text`)은 제거하고 permission 단언으로 대체(위 `test_catalog_text_contains_permissions`).

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py -q`
Expected: FAIL — `PermissionValidator.__init__() got an unexpected keyword argument 'permissions'`.

- [ ] **Step 3: `core/fga/permission_validator.py` 구현**

(a) 상단 `_CAPABILITY_RELATIONS`·`_KNOWN_TABLES` 상수 삭제. `__init__`·`from_config`·`validate`·`catalog_text` 교체:

```python
class PermissionValidator:
    def __init__(self, *, user_ids: set, departments: set, permissions: set) -> None:
        self._user_ids = user_ids
        self._departments = departments
        self._permissions = permissions

    @classmethod
    def from_config(
        cls,
        users_path: str = "config/users.yaml",
        permissions_path: str = "config/permissions.yaml",
    ) -> "PermissionValidator":
        users = yaml.safe_load(Path(users_path).read_text())["users"]
        user_ids = {u["user_id"] for u in users if u.get("user_id")}
        departments: set = set()
        for u in users:
            departments |= {d for d in u.get("departments", []) if d}
        perms_raw = yaml.safe_load(Path(permissions_path).read_text())["permissions"]
        permissions = {name for name in perms_raw.keys() if name}
        return cls(user_ids=user_ids, departments=departments, permissions=permissions)
```

> `from_config`는 `app/graph/tools/registry.py:28`에서 **무인자**로 호출되므로(`PermissionValidator.from_config()`) `folders_path`를 빼도 호출부 수정은 불필요하다.

(b) `_strip`/`_resolve_user`는 그대로 둔다. `validate` 교체:

```python
    def validate(self, parsed: dict) -> tuple | None:
        action = parsed.get("action")
        subject = parsed.get("subject", "")
        relation = parsed.get("relation", "")
        object_ = parsed.get("object", "")
        if action not in ("grant", "revoke"):
            return None
        if not all(isinstance(x, str) for x in (subject, relation, object_)):
            return None
        if any(" " in x for x in (subject, relation, object_)):
            return None

        if relation == "member":
            resolved = self._resolve_user(subject)
            dept = self._strip(object_, "department:")
            if resolved is None or dept not in self._departments:
                return None
            subject = resolved
        elif relation == "holder":
            perm = self._strip(object_, "permission:")
            if perm not in self._permissions:
                return None
            resolved = self._resolve_user(subject)
            if resolved is not None:
                subject = resolved
            else:
                # 부서/역할 묶음 배정: department:X#member 또는 role:X#member
                if subject.startswith("department:") and subject.endswith("#member"):
                    dept = subject[len("department:"):-len("#member")]
                    if dept not in self._departments:
                        return None
                elif subject.startswith("role:") and subject.endswith("#member"):
                    pass  # 역할 묶음은 c_level 등 — id 검증 생략(전역 역할은 소수·고정)
                else:
                    return None
        else:
            return None

        return (subject, relation, object_, action)

    def catalog_text(self) -> str:
        users = ", ".join(sorted(self._user_ids))
        depts = ", ".join(sorted(self._departments))
        perms = ", ".join(sorted(self._permissions))
        return f"유저: {users}\n부서: {depts}\n권한(permission): {perms}"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/fga/permission_validator.py tests/core/fga/test_permission_validator.py
git commit -m "feat(validator): holder(permission 배정) 화이트리스트 + dept_viewer/capability 분기 제거 (ADR-0051)"
```

---

## Task 4B: business DB·카탈로그·프롬프트·테스트 부서명 전면 정규화

> **추가 배경(2026-06-05 결정)**: 부서 id "팀" 제거가 OpenFGA 권한뿐 아니라 **business DB 데이터 도메인**에도 박혀 있음이 드러남(`employees.department`, `sales` 카테고리, 급여/장비 seed, SQL 프롬프트 안내). 사용자 결정 = **전면 통일**(권한=데이터, 둘 다 "개발"). Task 1이 권한쪽만 바꿔 생긴 11개 테스트 실패를 이 task가 해소한다.

**Files:**
- Modify: `core/sql/catalog.py`(EMPLOYEE_DEPARTMENTS·SALES_DEPARTMENTS·매핑 dict 키), `scripts/seed_business.py`(부서별 급여 dict·장비 부서), `app/graph/nodes/capability_node.py`(예시 텍스트), `app/graph/prompts.py`(SQL/라우터 예시 — **단 `PERMISSION_PARSE_PROMPT` 블록 L153-195는 Task 5에서 교체하므로 건드리지 말 것**)
- Modify(tests): 부서명 "XX팀"을 쓰는 모든 테스트 — `test_catalog.py`, `test_seed_business.py`, `test_auth.py`, `test_builder.py`, `test_jwt_handler.py`, `test_postgres_sink.py`, `test_audit_history_tool.py`, `test_justify_execute.py`, `test_prompts.py` 등

- [ ] **Step 1: 코드(비테스트) 부서명 정규화**

`개발팀→개발`, `제품팀→제품`, `재무팀→재무`, `영업팀→영업`, `법무팀→법무`, `인사팀→인사`, `디자인팀→디자인`. `PERMISSION_PARSE_PROMPT`(prompts.py L153-195)는 제외(Task 5):
```bash
# prompts.py는 PERMISSION_PARSE_PROMPT 외 라인만 — 수동 확인하며 치환(L86,87,128 등)
sed -i '' -E 's/(개발|제품|재무|영업|법무|인사|디자인)팀/\1/g' core/sql/catalog.py scripts/seed_business.py app/graph/nodes/capability_node.py
```
prompts.py는 L153-195를 건드리지 않도록 L86·L87·L128만 개별 수정.

- [ ] **Step 2: 테스트 부서명 정규화**
```bash
grep -rl '개발팀\|제품팀\|재무팀\|영업팀\|법무팀\|인사팀\|디자인팀' tests/ | xargs sed -i '' -E 's/(개발|제품|재무|영업|법무|인사|디자인)팀/\1/g'
```

- [ ] **Step 3: business DB 재시드 + 전체 테스트**
```bash
docker compose up -d postgres
.venv/bin/python -m scripts.seed_business   # employees/sales/equipment 재시드(정규화된 부서명)
.venv/bin/python -m pytest -q --tb=short
```
Expected: Task 1 도입 11 failed가 0으로. 남는 실패가 있으면 원인 분석(부서명 외 회귀인지 구분). test_builder의 justify 통합 실패가 부서명 mock 불일치였는지 확인.

- [ ] **Step 4: 잔재 확인 + Commit**
```bash
grep -rn '개발팀\|제품팀\|재무팀\|영업팀\|법무팀\|인사팀\|디자인팀' core/ scripts/ app/ tests/ config/ | grep -v PERMISSION_PARSE_PROMPT
# (PERMISSION_PARSE_PROMPT 잔재는 Task 5가 교체)
git add -A
git commit -m "feat(business): 부서명 전면 정규화(팀 제거) — 권한=데이터 통일 (ADR-0051)"
```

---

## Task 5: `prompts.py` — NL 파싱 규칙(유저→부서 번역 폐기)

**Files:**
- Modify: `app/graph/prompts.py` (`PERMISSION_PARSE_PROMPT`, L153-195)

> "유저에게 폴더 권한 → 부서 멤버십" 강제 번역(L169-173)을 폐기하고, "유저에게 권한 → permission holder 배정"으로 바꾼다. relation은 `member`(부서 멤버십)·`holder`(permission 배정) 두 가지.

- [ ] **Step 1: `PERMISSION_PARSE_PROMPT` 본문 교체**

```python
PERMISSION_PARSE_PROMPT = """\
다음 권한 관리 지시를 JSON으로 변환하라.

알려진 식별자(반드시 이 정확한 id를 사용):
{known_ids}

규칙:
- action: "grant"(부여), "revoke"(회수), "query"(조회)
- query 시: {{"action":"query","target_user_id":"<유저id 또는 null>"}}
  target_user_id가 없으면 null (본인 조회)
- grant/revoke 시 두 가지 relation만 사용:
  부서 멤버십: subject="user:<유저id>", relation="member", object="department:<부서>"
  권한 배정:   subject="user:<유저id>" 또는 "department:<부서>#member",
              relation="holder", object="permission:<권한>"

권한 배정 규칙(중요):
- "특정 유저에게 <권한/문서/폴더> 열람·접근 권한 부여" → 그 유저에게 해당 permission을 직접 배정한다(부서 가입이 아님).
  subject="user:<유저id>", relation="holder", object="permission:<권한>".
  예: "이민준에게 인사 문서 열람 권한" → subject="user:user-minjun", relation="holder", object="permission:인사"
  예: "박서연에게 재무 권한" → subject="user:user-seoyeon", relation="holder", object="permission:재무"
- "유저를 <부서>에 추가/소속" 처럼 부서 자체에 넣으라는 지시일 때만 relation="member".

id 매핑(반드시 위 '알려진 식별자'의 정확한 id로 변환):
- 비격식 이름·영문 단명·표시명(예: "지수", "joohwan", "노주환")은 반드시 정식 user id("user-joohwan")로 바꾼다.
- 권한명은 부서 id와 같다(예: 인사·개발·재무·법무·영업·제품). "인사 문서/권한"은 permission:인사.
- "추가/넣어/줘" → action "grant"; "제거/빼/회수" → action "revoke".
- 어느 id인지 카탈로그에서 확정할 수 없으면 추측하지 말고 가장 가까운 식별자를 그대로 둔다(검증기가 거른다).

예시:
- "노주환를 개발 부서에 추가" →
  {{"action":"grant","subject":"user:user-joohwan","relation":"member","object":"department:개발"}}
- "이민준에게 인사 문서 열람 권한 줘" →
  {{"action":"grant","subject":"user:user-minjun","relation":"holder","object":"permission:인사"}}
- "박서연 재무 권한 회수" →
  {{"action":"revoke","subject":"user:user-seoyeon","relation":"holder","object":"permission:재무"}}

grant/revoke 키: action, subject, relation, object 네 개.
query 키: action, target_user_id 두 개.
JSON 객체만 출력(설명·코드펜스 금지).

지시: {instruction}

JSON:"""
```

- [ ] **Step 2: 임포트·참조 정합 스모크**

Run: `.venv/bin/python -c "from app.graph.prompts import PERMISSION_PARSE_PROMPT; assert 'holder' in PERMISSION_PARSE_PROMPT and 'permission:' in PERMISSION_PARSE_PROMPT and 'dept_viewer' not in PERMISSION_PARSE_PROMPT; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add app/graph/prompts.py
git commit -m "feat(prompts): 권한 부여 NL을 permission holder 배정으로(부서 번역 폐기) (ADR-0051)"
```

---

## Task 6: `gate.py` + `client.py` — `dept_viewer`→`viewer` 개명

**Files:**
- Modify: `core/sql/gate.py` (`gate_table_access`), `core/fga/client.py` (`user_accessible_tables`)
- Test: `tests/core/sql/test_gate.py`

> 테이블 접근 Check의 relation 이름만 바꾼다. 로직·시그니처 불변. FGA가 `viewer = holder from gated_by`를 풀어 user→permission→table을 해소한다.

- [ ] **Step 1: 실패 테스트 갱신** — `test_gate.py`와 `test_client.py`의 `dept_viewer` mock을 `viewer`로

`tests/core/sql/test_gate.py`의 `_table_checker`(L101-105):
```python
def _table_checker(granted: set):
    """granted = viewer 보유 table 객체 집합(예: {"table:employees"})."""
    async def check(user, relation, object_):
        return relation == "viewer" and object_ in granted
    return check
```

`tests/core/fga/test_client.py`의 `user_accessible_tables` 테스트 3개(L297~333) — mock check의 `relation == "dept_viewer"`를 `relation == "viewer"`로 치환(L302, L316, 그리고 L325~333 블록 내). 단언은 그대로.

(`test_table_access_*` 단언은 그대로 — reason 문자열에 테이블명이 포함되는지만 본다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py -q`
Expected: FAIL — `test_table_access_all_present` 등에서 `gate_table_access`가 여전히 `dept_viewer`로 check해 `_table_checker`(viewer)와 어긋나 `ok is False`.

- [ ] **Step 3: 구현**

`core/sql/gate.py` `gate_table_access`(L79-83):
```python
    user = f"user:{user_id}"
    for table in sorted(tables):
        if not await check(user, "viewer", f"table:{table}"):
            return False, f"table:{table} viewer 미보유 → DENY"
    return True, "참조 테이블 viewer 전부 보유 → 통과"
```
docstring(L72)의 "dept_viewer를 AND로 확인" → "viewer를 AND로 확인", "dept_viewer 튜플이 없는" → "viewer가 없는".

`core/fga/client.py` `user_accessible_tables`(L97):
```python
        if await self.check(f"user:{user_id}", "viewer", f"table:{table}"):
```
docstring(L89)의 "dept_viewer 권한을 가진" → "viewer 권한을 가진".

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py tests/core/fga/test_client.py -q`
Expected: PASS. (test_client.py에 `dept_viewer` 단언이 있으면 `viewer`로 갱신.)

- [ ] **Step 5: Commit**

```bash
git add core/sql/gate.py core/fga/client.py tests/core/sql/test_gate.py tests/core/fga/test_client.py
git commit -m "refactor(fga): table 접근 relation dept_viewer→viewer 개명 (ADR-0051)"
```

---

## Task 7: 위임 승격 — permission 배정(팀장)

**Files:**
- Modify: `app/graph/tools/permission_tool.py` (`delegated_permission` 신설), `app/graph/nodes/tool_gate.py` (승격 분기 확장)
- Test: `tests/app/graph/tools/test_permission_tool.py`, `tests/app/graph/nodes/test_tool_gate.py`

> 부서 팀장(`department.admin`)이 **자기 부서가 보유한 permission을 개인(user:)에게 holder 배정**하면 DENY를 JUSTIFY_AND_APPROVE로 승격한다. 부서/역할 배정(정의급)이나 타 부서 permission은 승격하지 않는다(c_level 전용). 기존 멤버십 위임(ADR-0046)은 보존.

- [ ] **Step 1: `permission_tool.py` 위임 헬퍼 실패 테스트 작성**

`tests/app/graph/tools/test_permission_tool.py`: `_validator()`를 permission 시그니처로 바꾸고(부서명 정규화), 멤버십 위임 예시의 부서명 정규화, `delegated_permission` 테스트 신설.

```python
from app.graph.tools.permission_tool import (
    PermissionAgent,
    delegated_membership_dept,
    delegated_permission,
    _format_permission_snapshot,
    _resolve_capabilities,
)


def _validator():
    return PermissionValidator(
        user_ids={"user-joohwan"}, departments={"개발"}, permissions={"개발", "인사"}
    )


def test_delegated_permission_grant_to_user():
    assert delegated_permission("grant user:user-minjun holder permission:인사") == "인사"


def test_delegated_permission_revoke_to_user():
    assert delegated_permission("revoke user:user-minjun holder permission:인사") == "인사"


def test_delegated_permission_to_department_none():
    # 부서 전체 배정(정의급)은 위임 대상 아님 → None (c_level 전용)
    assert delegated_permission("grant department:개발#member holder permission:개발") is None


def test_delegated_permission_non_holder_none():
    assert delegated_permission("grant user:user-joohwan member department:개발") is None
    assert delegated_permission("query u1 u2") is None
```

기존 `test_delegated_membership_dept_*`의 부서명(`개발팀`→`개발`, `인사팀`→`인사`)과 `test_delegated_membership_dept_non_membership_none`의 dept_viewer 예시는 holder 예시로 갱신:
```python
def test_delegated_membership_dept_non_membership_none():
    # permission 배정·capability는 멤버십 위임 대상이 아니다 → None.
    assert delegated_membership_dept("grant user:user-joohwan holder permission:개발") is None
    assert delegated_membership_dept("grant user:user-joohwan justify_select capability:sql") is None
```

`test_plan_valid_grant_*`/`test_execute_*`의 `department:개발팀`→`department:개발`로 일괄. `_validator()` 호출은 시그니처 변경으로 자동 반영.

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -q`
Expected: FAIL — `ImportError: cannot import name 'delegated_permission'`.

- [ ] **Step 3: `permission_tool.py`에 `delegated_permission` 추가** (`delegated_membership_dept` 아래)

```python
def delegated_permission(planned_action: str) -> str | None:
    """permission 배정 위임 대상 권한 추출 (ADR-0051).

    `grant|revoke user:<U> holder permission:<X>` 형태(개인 배정)면 권한 id X를 반환한다.
    부서/역할 배정(subject가 user:가 아님)은 정의급이라 None — c_level 전용.
    게이트(tool_gate_node)가 요청자가 X를 보유한 부서의 admin인지로 승격을 판단한다.
    """
    parts = planned_action.split(" ")
    if len(parts) != 4:
        return None
    action, subject, relation, object_ = parts
    if action not in ("grant", "revoke") or relation != "holder":
        return None
    if not subject.startswith("user:"):
        return None
    prefix = "permission:"
    if not object_.startswith(prefix):
        return None
    return object_[len(prefix):] or None
```

- [ ] **Step 4: `permission_tool` 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -q`
Expected: PASS.

- [ ] **Step 5: `tool_gate.py` 승격 분기 실패 테스트 작성**

`tests/app/graph/nodes/test_tool_gate.py`: 모든 부서명 정규화(`영업팀`→`영업`, `인사팀`→`인사`, `개발팀`→`개발`), `dept_viewer`→`viewer`. `test_table_gate_allows_select_with_dept_viewer`의 tuples를 `{("viewer", "table:employees")}`로, `_fga(..., ["인사"], ...)`로. 멤버십 위임 테스트 부서명 정규화. `test_dept_admin_cannot_delegate_dept_viewer`를 아래 두 케이스로 교체:

```python
@pytest.mark.asyncio
async def test_dept_admin_permission_delegation_upgrades_to_justify():
    """팀장이 자기 부서(개발)가 보유한 permission:개발을 개인에게 배정 → JUSTIFY 승격 (ADR-0051)."""
    handler = _handler("grant user:user-x holder permission:개발", "grant")
    state = {
        "user_id": "팀장", "question": "q",
        "agent_messages": [_ai([{"name": "manage_permission", "args": {"instruction": "x"}, "id": "p1"}])],
    }
    out = await tool_gate_node(
        state, registry=_perm_registry(handler),
        # 전역 justify_grant 없음. admin@department:개발 + department:개발#member가 permission:개발 holder.
        fga_client=_fga([], ["개발"], tuples={("admin", "department:개발"), ("holder", "permission:개발")}),
        audit_sink=AsyncMock(),
    )
    assert out["pending_tool_calls"]
    assert out["pending_tool_calls"][0]["decision"] == "JUSTIFY_AND_APPROVE"
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_dept_admin_cannot_delegate_permission_to_department():
    """부서 전체 배정(정의급)은 팀장이 못 한다 → DENY (c_level 전용, ADR-0051)."""
    handler = _handler("grant department:개발#member holder permission:개발", "grant")
    state = {
        "user_id": "팀장", "question": "q",
        "agent_messages": [_ai([{"name": "manage_permission", "args": {"instruction": "x"}, "id": "p2"}])],
    }
    out = await tool_gate_node(
        state, registry=_perm_registry(handler),
        fga_client=_fga([], ["개발"], tuples={("admin", "department:개발"), ("holder", "permission:개발")}),
        audit_sink=AsyncMock(),
    )
    assert not out["pending_tool_calls"]
    handler.execute.assert_not_called()
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -q`
Expected: FAIL — `test_dept_admin_permission_delegation_upgrades_to_justify`가 승격 분기 부재로 `pending_tool_calls` 비어 실패.

- [ ] **Step 7: `tool_gate.py` 승격 분기 확장** (L14 import + L72-76)

import 추가:
```python
from app.graph.tools.permission_tool import delegated_membership_dept, delegated_permission
```

승격 블록 교체:
```python
        # 권한 위임 승격: 전역 grant 권한 없는 DENY를, 부서 admin이면 JUSTIFY_AND_APPROVE로.
        if decision == DECISION_DENY and risk == RISK_GRANT:
            # (1) 부서 멤버십 위임 (ADR-0046)
            dept = delegated_membership_dept(planned_action)
            if dept and await fga_client.check(f"user:{user_id}", "admin", f"department:{dept}"):
                decision = DECISION_JUSTIFY_AND_APPROVE
                reason = f"부서 admin 멤버십 위임(department:{dept}) → JUSTIFY_AND_APPROVE"
            else:
                # (2) permission 배정 위임 (ADR-0051): 자기 부서가 holder인 permission을 개인에 배정
                perm = delegated_permission(planned_action)
                if perm:
                    for d in departments:
                        if await fga_client.check(f"user:{user_id}", "admin", f"department:{d}") and \
                           await fga_client.check(f"department:{d}#member", "holder", f"permission:{perm}"):
                            decision = DECISION_JUSTIFY_AND_APPROVE
                            reason = f"부서 admin permission 위임(department:{d}→permission:{perm}) → JUSTIFY_AND_APPROVE"
                            break
```
(`departments`는 함수 시작부 L41 `departments = await fga_client.user_departments(user_id)`를 재사용.)

- [ ] **Step 8: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py tests/app/graph/tools/test_permission_tool.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/graph/tools/permission_tool.py app/graph/nodes/tool_gate.py tests/app/graph/tools/test_permission_tool.py tests/app/graph/nodes/test_tool_gate.py
git commit -m "feat(gate): permission 배정 위임 승격(팀장 자기 부서 한정) (ADR-0051)"
```

---

## Task 8: 통합 스모크 + 전체 회귀 + eval

**Files:**
- Create(임시): `scripts/_smoke_perm.py` (검증 후 삭제)

> 실제 OpenFGA를 띄워 big bang 모델·시드를 적용하고, permission 모델의 핵심 동작(부서 경로 보존 + 개인 배정 + 경계)을 검증한다.

- [ ] **Step 1: OpenFGA/Postgres 기동 + 모델·시드 적용 (big bang)**

```bash
docker compose up -d            # openfga, postgres (docker-compose.yml 기준)
./scripts/fga_init.sh           # fga/model.json 업로드 (새 permission 모델)
.venv/bin/python -m scripts.seed_fga --prune   # 새 튜플 시드 + 옛 dept_viewer/department:인사팀 stale 정리
```
Expected: fga_init "모델 업로드 완료", seed "FGA 시드 완료 (... 튜플, prune N 삭제)".

- [ ] **Step 2: 권한 시나리오 검증 스크립트 작성·실행** — `scripts/_smoke_perm.py`

```python
import asyncio
import asyncpg
from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig


async def main():
    cfg = load_config()
    pool = await asyncpg.create_pool(cfg.postgres_dsn)
    fc = FGAConfig(api_url=cfg.fga_api_url, store_id=cfg.fga_store_id,
                   api_key=cfg.fga_api_key, cache_ttl_seconds=0)
    c = FGAClient(config=fc, cache=make_cache_backend(cfg.fga_cache_backend, pool), pg_pool=pool)

    # 1) 부서 경로 보존: minjun(인사 부서원) → /company/hr 열람
    assert await c.check("user:user-minjun", "can_read", "folder:/company/hr"), "부서 경로 실패"
    # 2) 개인 배정(부서 미가입): seoyeon(departments=[]) → permission:인사 직접 배정 → /company/hr
    assert not await c.check("user:user-seoyeon", "can_read", "folder:/company/hr"), "사전조건 위반"
    await c.grant_tuple("user:user-seoyeon", "holder", "permission:인사")
    assert await c.check("user:user-seoyeon", "can_read", "folder:/company/hr"), "개인 배정 실패"
    await c.revoke_tuple("user:user-seoyeon", "holder", "permission:인사")
    assert not await c.check("user:user-seoyeon", "can_read", "folder:/company/hr"), "회수 실패"
    # 3) 테이블 경계: minho(영업) → sales 허용, employees(PII) 거부
    assert await c.check("user:user-minho", "viewer", "table:sales"), "영업 sales 실패"
    assert not await c.check("user:user-minho", "viewer", "table:employees"), "영업 employees 경계 실패"
    # 4) 전직원 기본 SELECT: permission:기본(holder user:*) → 누구나 allow_select
    assert await c.check("user:user-seoyeon", "allow_select", "capability:sql"), "기본 SELECT 실패"
    # 5) private 보장: seoyeon은 공개 폴더만, 법무 private은 막힘
    assert not await c.check("user:user-seoyeon", "can_read", "folder:/company/legal"), "private 누수"
    # 6) c_level super_reader: admin은 private 관통
    assert await c.check("user:user-admin", "can_read", "folder:/company/legal"), "c_level 관통 실패"

    await pool.close()
    print("✅ 통합 검증 OK (6/6)")


asyncio.run(main())
```

Run: `.venv/bin/python scripts/_smoke_perm.py`
Expected: `✅ 통합 검증 OK (6/6)`.

- [ ] **Step 3: 임시 스크립트 삭제 + 전체 단위 테스트**

```bash
rm scripts/_smoke_perm.py
.venv/bin/python -m pytest -q
```
Expected: 전체 PASS. 실패 시 해당 테스트의 부서명/relation 잔재(`dept_viewer`, `개발팀` 등)를 찾아 갱신. `grep -rn 'dept_viewer\|인사팀\|개발팀\|재무팀\|영업팀\|제품팀\|법무팀\|디자인팀' tests/ app/ core/ scripts/`로 잔재 확인.

- [ ] **Step 4: eval 회귀**

Run: `.venv/bin/python -m tests.eval.runner`(또는 `tests/eval/runner.py`)
Expected: 기존 부서 기반 접근 시나리오 점수 유지. 하락 시 원인 명시 — eval 하니스 자체의 선재 버그(지표 타입·`compare_reranker` 미배선, `project_eval_harness_debt` 메모 참고) 가능성과 구분할 것. eval 시나리오가 부서명(`인사팀` 등)을 하드코딩하면 정규화에 맞춰 갱신.

- [ ] **Step 5: Commit** (테스트 잔재 수정이 있었으면)

```bash
git add -A
git commit -m "test: permission 모델 전환에 따른 테스트 잔재(부서명/relation) 정리 (ADR-0051)"
```

---

## Task 9: ADR — 0051 신규 + 0046/0015/0050 갱신

**Files:**
- Create: `docs/superpowers/decisions/ADR-0051-permission-node-separation.md`
- Modify: `ADR-0046`/`ADR-0015`/`ADR-0050`(상태·본문), `decisions/README.md`(자동생성), `backend/CLAUDE.md`(FGA 항목)

- [ ] **Step 1: ADR-0051 작성** — `docs/superpowers/decisions/_template.md` 형식. 제목 바로 아래 `> **Status**: 🟢 적용완료`. 포함 내용:
  - **맥락**: 권한 부여가 부서 멤버십과 결합(`folder.dept_viewer:[department#member]`) → 개인에게 권한만 주려면 부서 통째 가입, 최소권한 위반.
  - **결정**: `type permission`(holder=[user, user:*, department#member, role#member]) 1급 노드 도입. folder/table을 `gated_by`→`viewer = holder from gated_by`(TTU)로 permission 경유. capability를 `permission#holder`로 통일. 부서 id 정규화(팀 제거)로 `permission:인사 = department:인사`. 위임은 정의(c_level)/배정(c_level+팀장 자기 부서 한정) 분리.
  - **이유**: 검색/실행 코드 불변(FGA가 user→permission→resource 해소), permission이 folder/table 물리통합 없이 추상 레이어 역할, private 보장 직교 유지.
  - **대안**: 부서 완전 분리(마이그레이션 큼)·access_group 신설(permission이 더 명시적) 기각.
  - **영향**: ADR-0046 대체, 0015·0050 개정. spec 링크: `docs/superpowers/specs/2026-06-05-permission-department-separation-design.md`.

- [ ] **Step 2: 관련 ADR 상태·본문 갱신**
  - `ADR-0046`: Status를 `🟣 대체됨 → [ADR-0051](ADR-0051-permission-node-separation.md)`로. 본문 상단에 "위임 단위가 멤버십→permission 배정으로 재설계됨" 한 줄.
  - `ADR-0015`: 본문에 "후속: `dept_viewer`는 ADR-0051에서 `viewer`(permission 경유)로 전환. pre-filter 메커니즘은 불변." 추가.
  - `ADR-0050`: 본문 드리프트("개인 직접 부여 불가"가 라이브와 모순) 정리 — "ADR-0051에서 table도 permission#holder 경유로 통일, 개인 배정은 permission으로 표현" 추가.

- [ ] **Step 3: 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성(ADR-0051 등재, 0046 대체됨 배지).

- [ ] **Step 4: `backend/CLAUDE.md` FGA 항목 갱신** — "핵심 아키텍처 결정"의 FGA 줄에 permission 노드·viewer 개명 반영, 위임(ADR-0046) 줄을 ADR-0051로 갱신.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/decisions/ docs/superpowers/specs/ backend/CLAUDE.md
git commit -m "docs(adr): ADR-0051 permission 노드 분리 + 0046 대체·0015/0050 개정"
```

---

## DoD 체크리스트 (완료 기준)

- [ ] 모든 Task 단위 테스트 PASS (`.venv/bin/python -m pytest -q`)
- [ ] 통합 스모크 6/6 (Task 8 Step 2)
- [ ] eval 회귀 — 점수 유지(하락 시 원인 명시)
- [ ] `grep dept_viewer fga/ app/ core/ scripts/` 잔재 0 (justify_grant 등 의도적 잔존 제외)
- [ ] `grep '인사팀\|개발팀\|...' config/ app/ core/ scripts/ tests/` 잔재 0
- [ ] ADR-0051 작성 + 0046/0015/0050 갱신 + `gen_adr_index` 실행
- [ ] `backend/CLAUDE.md` FGA·위임 항목 갱신
- [ ] PR 생성 (description에 위 DoD)

> **마이그레이션 주의(big bang)**: 운영 store에서는 `seed_fga.py --prune`이 옛 `department:인사팀` 멤버십·`dept_viewer` 폴더 튜플을 삭제한다. 프론트 표시명이 "인사팀"에 의존하면 별도 표시명 매핑이 필요(spec §9). 데모 시나리오(`project_demo_scenario`)의 부서명도 갱신 대상.
