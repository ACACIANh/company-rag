# 직원 30명 확장 + 부서별 팀장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실계정 직원을 12명 → 30명으로 늘리고, 7개 실부서 각각에 팀장(`dept_admin`)을 두며, 팀장을 `employees.position='팀장'`에도 반영한다.

**Architecture:** 시드 스크립트(`seed_business.py`/`seed_fga.py`)는 `config/users.yaml`을 순회하는 데이터 주도 구조다. 따라서 계정 추가 + `dept_admin_of` 부여는 대부분 yaml 편집만으로 끝난다. 팀장을 DB position에 노출하려면 `catalog.POSITIONS`와 `build_employee_rows`의 position 결정 로직만 소폭 변경한다.

**Tech Stack:** Python 3.11, pytest, PyYAML, asyncpg, OpenFGA (시드는 데이터 주도).

작업 디렉토리는 모두 `backend/`. 인터프리터는 `.venv/bin/python`.

---

## 사전 작업: feature 브랜치

- [ ] **브랜치 생성**

```bash
cd /Users/acacian/vscode/company-rag && git checkout -b feat/headcount-expansion
```

---

### Task 1: catalog.POSITIONS에 '팀장' 추가

**Files:**
- Modify: `backend/core/sql/catalog.py` (POSITIONS 정의)
- Test: `backend/tests/scripts/test_seed_business.py` (catalog 검사 테스트 영역)

- [ ] **Step 1: 실패 테스트 작성**

`tests/scripts/test_seed_business.py`의 `# ── catalog equipment constants ──` 영역 근처에 추가:

```python
def test_catalog_positions_includes_team_lead():
    assert "팀장" in catalog.POSITIONS
    # position 값 힌트(NL→SQL)에 팀장이 노출되어야 한다
    assert "팀장" in catalog.CATEGORICAL_VALUES["business.employees.position"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_catalog_positions_includes_team_lead -v`
Expected: FAIL — `assert "팀장" in ["CTO", "팀원"]`

- [ ] **Step 3: 최소 구현**

`backend/core/sql/catalog.py`의 POSITIONS 한 줄을 수정:

```python
# 직급 리터럴
POSITIONS = ["CTO", "팀원", "팀장"]
```

(`CATEGORICAL_VALUES["business.employees.position"]`는 이미 `POSITIONS`를 참조하므로 자동 반영. `POSITIONS[0]`/`POSITIONS[1]` 인덱스 의미는 보존된다.)

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_catalog_positions_includes_team_lead -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/core/sql/catalog.py backend/tests/scripts/test_seed_business.py && git commit -m "feat(catalog): POSITIONS에 '팀장' 직급 추가"
```

---

### Task 2: build_employee_rows position 로직 — 팀장 반영

**Files:**
- Modify: `backend/scripts/seed_business.py` (`build_employee_rows`, line ~52-64)
- Test: `backend/tests/scripts/test_seed_business.py` (build_employee_rows 영역)

- [ ] **Step 1: 실패 테스트 작성**

`# ── build_employee_rows ──` 영역에 추가:

```python
def test_employee_position_team_lead_for_dept_admin():
    rows = build_employee_rows([
        {"username": "lead", "user_id": "user-lead",
         "departments": ["개발"], "dept_admin_of": ["개발"]},
    ])
    # (emp_id, name, department, position, ...)
    assert rows[0][3] == "팀장"


def test_employee_position_member_for_plain_user():
    rows = build_employee_rows([
        {"username": "plain", "user_id": "user-plain", "departments": ["개발"]},
    ])
    assert rows[0][3] == "팀원"


def test_employee_position_cto_for_exec():
    rows = build_employee_rows([
        {"username": "boss", "user_id": "user-boss", "fga_roles": ["c_level"]},
    ])
    assert rows[0][3] == "CTO"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_employee_position_team_lead_for_dept_admin -v`
Expected: FAIL — position이 "팀원"으로 나옴 (`assert "팀원" == "팀장"`)

- [ ] **Step 3: 최소 구현**

`backend/scripts/seed_business.py`의 `build_employee_rows` 안에서 position 결정 줄을 교체.

기존:
```python
        is_exec = "c_level" in (user.get("fga_roles") or [])
        position = catalog.POSITIONS[0] if is_exec else catalog.POSITIONS[1]
```

변경:
```python
        is_exec = "c_level" in (user.get("fga_roles") or [])
        is_lead = bool(user.get("dept_admin_of"))
        if is_exec:
            position = "CTO"
        elif is_lead:
            position = "팀장"
        else:
            position = "팀원"
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py -v`
Expected: PASS (신규 3개 + 기존 employee 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/scripts/seed_business.py backend/tests/scripts/test_seed_business.py && git commit -m "feat(seed): dept_admin_of 보유 직원 position을 '팀장'으로"
```

---

### Task 3: 기존 6개 계정에 dept_admin_of 부여 (팀장 6명)

**Files:**
- Modify: `backend/config/users.yaml` (dohyeon, minho, minjun, jiyoung, subin, yujin)

jisoo(개발)는 이미 `dept_admin_of: [개발]` 보유 → 무변경.

- [ ] **Step 1: yaml 편집**

다음 6개 계정 각각의 `roles: [user]` 줄 아래에 `dept_admin_of` 한 줄을 추가한다(부서명은 해당 계정의 `departments`와 동일).

- minjun(인사): `    dept_admin_of: [인사]   # 부서 팀장 (ADR-0046/0051)`
- dohyeon(제품): `    dept_admin_of: [제품]   # 부서 팀장 (ADR-0046/0051)`
- yujin(디자인): `    dept_admin_of: [디자인]   # 부서 팀장 (ADR-0046/0051)`
- minho(영업): `    dept_admin_of: [영업]   # 부서 팀장 (ADR-0046/0051)`
- jiyoung(재무): `    dept_admin_of: [재무]   # 부서 팀장 (ADR-0046/0051)`
- subin(법무): `    dept_admin_of: [법무]   # 부서 팀장 (ADR-0046/0051)`

예시 (minjun):
```yaml
  - username: minjun
    password: minjun123
    user_id: user-minjun
    roles: [user]
    departments: [인사]
    dept_admin_of: [인사]   # 부서 팀장 (ADR-0046/0051)
    display_name: 이민준
    email: minjun.lee@techcorp.example
```

- [ ] **Step 2: 커밋** (Task 4와 함께 검증 후 커밋하므로 여기선 보류 — 아래 Task 5 데이터 검증 후 일괄 커밋)

---

### Task 4: 신규 18개 계정 추가

**Files:**
- Modify: `backend/config/users.yaml` (말미에 18개 항목 추가)

- [ ] **Step 1: yaml 말미에 추가**

`users.yaml`의 `taeyang` 항목 다음(파일 끝)에 아래 18개 블록을 그대로 추가:

```yaml
  - username: dowoon
    password: dowoon123
    user_id: user-dowoon
    roles: [user]
    departments: [개발]
    display_name: 김도윤
    email: dowoon.kim@techcorp.example
  - username: seojin
    password: seojin123
    user_id: user-seojin
    roles: [user]
    departments: [개발]
    display_name: 이서진
    email: seojin.lee@techcorp.example
  - username: hajun
    password: hajun123
    user_id: user-hajun
    roles: [user]
    departments: [개발]
    display_name: 박하준
    email: hajun.park@techcorp.example
  - username: siwoo
    password: siwoo123
    user_id: user-siwoo
    roles: [user]
    departments: [개발]
    display_name: 정시우
    email: siwoo.jung@techcorp.example
  - username: yejun
    password: yejun123
    user_id: user-yejun
    roles: [user]
    departments: [제품]
    display_name: 최예준
    email: yejun.choi@techcorp.example
  - username: juwon
    password: juwon123
    user_id: user-juwon
    roles: [user]
    departments: [제품]
    display_name: 강주원
    email: juwon.kang@techcorp.example
  - username: jiho
    password: jiho123
    user_id: user-jiho
    roles: [user]
    departments: [제품]
    display_name: 윤지호
    email: jiho.yoon@techcorp.example
  - username: eunwoo
    password: eunwoo123
    user_id: user-eunwoo
    roles: [user]
    departments: [영업]
    display_name: 임은우
    email: eunwoo.lim@techcorp.example
  - username: yuchan
    password: yuchan123
    user_id: user-yuchan
    roles: [user]
    departments: [영업]
    display_name: 한유찬
    email: yuchan.han@techcorp.example
  - username: sunwoo
    password: sunwoo123
    user_id: user-sunwoo
    roles: [user]
    departments: [영업]
    display_name: 오선우
    email: sunwoo.oh@techcorp.example
  - username: sua
    password: sua123
    user_id: user-sua
    roles: [user]
    departments: [인사]
    display_name: 이수아
    email: sua.lee@techcorp.example
  - username: jiyu
    password: jiyu123
    user_id: user-jiyu
    roles: [user]
    departments: [인사]
    display_name: 박지유
    email: jiyu.park@techcorp.example
  - username: serin
    password: serin123
    user_id: user-serin
    roles: [user]
    departments: [재무]
    display_name: 정세린
    email: serin.jung@techcorp.example
  - username: yerin
    password: yerin123
    user_id: user-yerin
    roles: [user]
    departments: [재무]
    display_name: 최예린
    email: yerin.choi@techcorp.example
  - username: minseo
    password: minseo123
    user_id: user-minseo
    roles: [user]
    departments: [법무]
    display_name: 강민서
    email: minseo.kang@techcorp.example
  - username: chaeeun
    password: chaeeun123
    user_id: user-chaeeun
    roles: [user]
    departments: [법무]
    display_name: 윤채은
    email: chaeeun.yoon@techcorp.example
  - username: jian
    password: jian123
    user_id: user-jian
    roles: [user]
    departments: [디자인]
    display_name: 신지안
    email: jian.shin@techcorp.example
  - username: harin
    password: harin123
    user_id: user-harin
    roles: [user]
    departments: [디자인]
    display_name: 김하린
    email: harin.kim@techcorp.example
```

- [ ] **Step 2: yaml 파싱 확인**

Run:
```bash
cd backend && .venv/bin/python -c "import yaml; d=yaml.safe_load(open('config/users.yaml')); print(len(d['users']))"
```
Expected: `30`

---

### Task 5: users.yaml 데이터 무결성 가드 테스트

**Files:**
- Create: `backend/tests/config/__init__.py` (없으면)
- Create: `backend/tests/config/test_users_yaml.py`

`users.yaml`이 구조 불변식(30계정·7팀장·username 유일)을 만족하는지 잠그는 테스트. 시드 두 스크립트를 모두 통과시켜 employees 30행 + 팀장 7튜플을 교차 검증한다.

- [ ] **Step 1: 테스트 작성**

`backend/tests/config/test_users_yaml.py`:

```python
from pathlib import Path

import yaml

from scripts.seed_business import build_employee_rows
from scripts.seed_fga import _build_tuples

_USERS_YAML = Path(__file__).resolve().parents[2] / "config" / "users.yaml"
_REAL_DEPTS = {"개발", "제품", "영업", "인사", "재무", "법무", "디자인"}


def _load():
    return yaml.safe_load(_USERS_YAML.read_text())["users"]


def test_users_yaml_has_thirty_accounts():
    assert len(_load()) == 30


def test_employee_rows_total_thirty():
    rows = build_employee_rows(_load())
    assert len(rows) == 30


def test_usernames_and_user_ids_unique():
    users = _load()
    usernames = [u["username"] for u in users]
    user_ids = [u["user_id"] for u in users]
    assert len(set(usernames)) == 30
    assert len(set(user_ids)) == 30


def test_exactly_one_team_lead_per_real_department():
    users = _load()
    leads_by_dept: dict[str, list[str]] = {}
    for u in users:
        for dept in u.get("dept_admin_of", []) or []:
            leads_by_dept.setdefault(dept, []).append(u["username"])
    # 7개 실부서 각각 정확히 1명의 팀장
    assert set(leads_by_dept) == _REAL_DEPTS
    for dept, leads in leads_by_dept.items():
        assert len(leads) == 1, f"{dept} 팀장이 {leads}로 1명이 아님"


def test_each_team_lead_is_member_of_its_department():
    # dept_admin_of 부서는 본인 departments에 포함되어야 한다(고아 위임 방지)
    for u in _load():
        for dept in u.get("dept_admin_of", []) or []:
            assert dept in (u.get("departments") or []), f"{u['username']} 위임 부서 모순"


def test_fga_emits_seven_dept_admin_tuples():
    tuples = _build_tuples(_load(), {}, {})
    admin_tuples = [
        t for t in tuples
        if t["relation"] == "admin" and t["object"].startswith("department:")
    ]
    assert len(admin_tuples) == 7
```

- [ ] **Step 2: `__init__.py` 보장**

Run:
```bash
cd backend && test -f tests/config/__init__.py || touch tests/config/__init__.py
```

- [ ] **Step 3: 테스트 실행 (Task 3·4 편집 검증)**

Run: `cd backend && .venv/bin/python -m pytest tests/config/test_users_yaml.py -v`
Expected: PASS (7개 테스트 전부) — 30계정·7팀장·유일성·멤버십 정합 확인

- [ ] **Step 4: 전체 시드 테스트 회귀**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/ tests/config/ -v`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 5: 커밋 (Task 3·4·5 일괄)**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/config/users.yaml backend/tests/config/ && git commit -m "feat(seed): 직원 30명 확장 + 부서별 팀장 7명(dept_admin_of) + 무결성 가드"
```

---

### Task 6: 전체 테스트 스위트 회귀 확인

**Files:** 없음 (검증만)

- [ ] **Step 1: 백엔드 전체 단위 테스트**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 전부 PASS. position 값 힌트('팀장') 추가가 다른 프롬프트/카탈로그 테스트를 깨지 않는지 확인.

- [ ] **Step 2: (선택) eval 회귀** — DoD 항목. eval 하니스가 동작 가능한 환경이면:

Run: `cd backend && .venv/bin/python -m tests.eval.runner` (또는 프로젝트 표준 명령)
Expected: 회귀 점수 비하락. 인원 확장은 권한/검색 로직 무변경이라 영향 없어야 한다. (DB/FGA·eval 미가동 환경이면 생략하고 PR에 명시.)

---

## 적용(re-seed) — 코드 변경과 별개, DB/FGA 가동 환경에서

> 단위 테스트는 DB 없이 통과한다. 실제 데이터 반영은 사용자 환경에서 수행.

```bash
cd backend && .venv/bin/python -m scripts.seed_business   # employees 30행 (TRUNCATE 후 재삽입)
cd backend && .venv/bin/python -m scripts.seed_fga        # 멤버십 + 팀장 admin 튜플 (멱등 추가)
```

`--prune`는 운영 중 manage_permission으로 추가된 튜플도 지우므로 일상 적용엔 쓰지 않는다(ADR-0044).

---

## Self-Review

**Spec coverage:**
- 30명 실계정 → Task 4 + Task 5(가드) ✅
- 7개 부서 팀장 → Task 3 + Task 5(7튜플 가드) ✅
- 팀장 employees.position 반영 → Task 1(catalog) + Task 2(로직) ✅
- seed_fga 무변경 → 확인됨(dept_admin_of 로직 기존 존재) ✅
- 변경 파일 = users.yaml/catalog.py/seed_business.py + 테스트 → 일치 ✅

**Placeholder scan:** 없음. 모든 코드/명령/기대출력 명시.

**Type consistency:** position 문자열 리터럴("CTO"/"팀원"/"팀장")이 catalog.POSITIONS·seed_business·테스트에서 동일. `dept_admin_of` 키 일관. `_build_tuples` 시그니처 `(users, folders, permissions)` 정확.
