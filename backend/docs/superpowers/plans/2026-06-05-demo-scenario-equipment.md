# 데모 시나리오 — equipment 테이블 추가 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `business.equipment` 테이블을 추가하고 FGA·카탈로그·검증기를 연동해, 6장면 데모 시나리오(장비 조회 → HITL 지급 → 권한부여 → 재검색 성공)가 실제로 동작하게 한다.

**Architecture:** 기존 `employees`·`sales` 테이블 구조와 동일하게 `seed_business.py`에 DDL + 시드 함수를 추가하고, `seed_fga.py`의 `_TABLE_GRANTS`에 `table:equipment` 튜플을 추가한다. `catalog.py`·`permission_validator.py`·`sql_tool.py`의 상수를 갱신해 카탈로그 힌트·검증·설명을 동기화한다.

**Tech Stack:** Python 3.11, asyncpg, PyYAML, pytest (단위), `cd backend && .venv/bin/python -m scripts.seed_business`

---

## 수정 파일 목록

| 파일 | 역할 |
|------|------|
| `core/sql/catalog.py` | equipment 카테고리·상태 상수 + CATEGORICAL_VALUES 항목 추가 |
| `scripts/seed_business.py` | equipment DDL + `build_equipment_rows()` + `main()` 연결 |
| `scripts/seed_fga.py` | `_TABLE_GRANTS`에 `table:equipment` 튜플 추가 |
| `core/fga/permission_validator.py` | `_KNOWN_TABLES`에 `"equipment"` 추가 |
| `app/graph/tools/sql_tool.py` | `_DESCRIPTION`에 equipment 언급 추가 |
| `docs/company/legal/employment-contract-template.md` | 근로계약서 표준 양식 문서 신규 생성 (RAG 검색 대상) |
| `tests/scripts/test_seed_business.py` | `build_equipment_rows` 단위 테스트 추가 |

---

## Task 1: catalog.py — equipment 상수 추가

**Files:**
- Modify: `core/sql/catalog.py`
- Test: `tests/scripts/test_seed_business.py` (catalog import로 간접 검증)

- [ ] **Step 1: 실패 테스트 작성**

`tests/scripts/test_seed_business.py` 상단에 추가:

```python
from core.sql import catalog

def test_catalog_has_equipment_categories():
    assert "노트북" in catalog.EQUIPMENT_CATEGORIES
    assert "모니터" in catalog.EQUIPMENT_CATEGORIES

def test_catalog_has_equipment_statuses():
    assert "미배정" in catalog.EQUIPMENT_STATUSES
    assert "수리중" in catalog.EQUIPMENT_STATUSES

def test_catalog_equipment_in_categorical_values():
    assert "business.equipment.category" in catalog.CATEGORICAL_VALUES
    assert "business.equipment.status" in catalog.CATEGORICAL_VALUES
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_catalog_has_equipment_categories -v
```

예상: `AttributeError: module 'core.sql.catalog' has no attribute 'EQUIPMENT_CATEGORIES'`

- [ ] **Step 3: catalog.py에 상수 추가**

`core/sql/catalog.py`의 `POSITIONS` 선언 바로 아래에 추가:

```python
# 장비 카테고리 / 상태
EQUIPMENT_CATEGORIES = ["노트북", "모니터", "서버", "기타"]
EQUIPMENT_STATUSES   = ["정상", "수리중", "폐기예정", "미배정"]
```

그리고 `CATEGORICAL_VALUES` dict에 항목 추가:

```python
CATEGORICAL_VALUES = {
    "business.employees.department": DEPARTMENTS,
    "business.employees.position": POSITIONS,
    "business.sales.period": SALES_PERIODS,
    "business.sales.department": SALES_DEPARTMENTS,
    "business.sales.product": sorted(set(DEPT_PRODUCT.values())),
    # equipment
    "business.equipment.category":     EQUIPMENT_CATEGORIES,
    "business.equipment.status":       EQUIPMENT_STATUSES,
    "business.equipment.assigned_dept": DEPARTMENTS,
}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_catalog_has_equipment_categories tests/scripts/test_seed_business.py::test_catalog_has_equipment_statuses tests/scripts/test_seed_business.py::test_catalog_equipment_in_categorical_values -v
```

예상: 3개 PASSED

- [ ] **Step 5: 커밋**

```bash
cd backend && git add core/sql/catalog.py tests/scripts/test_seed_business.py
git commit -m "feat(catalog): equipment 카테고리·상태 상수 + CATEGORICAL_VALUES 추가"
```

---

## Task 2: seed_business.py — equipment 테이블 DDL + 시드

**Files:**
- Modify: `scripts/seed_business.py`
- Test: `tests/scripts/test_seed_business.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/scripts/test_seed_business.py`에 추가:

```python
from scripts.seed_business import build_equipment_rows

def test_equipment_rows_nonempty():
    rows = build_equipment_rows()
    assert len(rows) >= 5

def test_equipment_rows_has_unassigned_laptop():
    rows = build_equipment_rows()
    # 장면 ③에 필요: status=미배정, category=노트북, assigned_to=None
    unassigned_laptops = [
        r for r in rows
        if r[2] == "노트북" and r[3] == "미배정" and r[6] is None
    ]
    assert len(unassigned_laptops) >= 2

def test_equipment_rows_has_nb001():
    rows = build_equipment_rows()
    ids = [r[0] for r in rows]
    assert "NB-001" in ids

def test_equipment_rows_deterministic():
    assert build_equipment_rows() == build_equipment_rows()

def test_equipment_row_shape():
    # (asset_id, name, category, status, assigned_dept, purchase_date, assigned_to)
    row = build_equipment_rows()[0]
    assert len(row) == 7
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_equipment_rows_nonempty -v
```

예상: `ImportError: cannot import name 'build_equipment_rows'`

- [ ] **Step 3: seed_business.py에 DDL 추가**

`_DDL` 문자열 안에 아래를 추가 (기존 `business.sales` CREATE TABLE 아래):

```python
_DDL = """
...기존 DDL 유지...

CREATE TABLE IF NOT EXISTS business.equipment (
    asset_id      text PRIMARY KEY,
    name          text NOT NULL,
    category      text NOT NULL,   -- 노트북 / 모니터 / 서버 / 기타
    status        text NOT NULL,   -- 정상 / 수리중 / 폐기예정 / 미배정
    assigned_dept text,            -- 담당 부서 (NULL = 미배정)
    purchase_date date NOT NULL,
    assigned_to   text             -- emp_id (NULL = 미배정)
);
"""
```

- [ ] **Step 4: build_equipment_rows 함수 추가**

`scripts/seed_business.py`에서 `build_sales_rows()` 함수 아래에 추가:

```python
from datetime import date

def build_equipment_rows() -> list[tuple]:
    """business.equipment 시드 행. 결정론적 합성. 미배정 노트북 2개 이상 보장."""
    return [
        # (asset_id, name, category, status, assigned_dept, purchase_date, assigned_to)
        ("NB-001", "맥북 프로 14인치",   "노트북", "미배정", None,    date(2024, 1, 10), None),
        ("NB-002", "맥북 에어 M3",        "노트북", "미배정", None,    date(2024, 3, 15), None),
        ("NB-003", "레노버 ThinkPad X1", "노트북", "수리중", "인사팀", date(2022, 1, 15), None),
        ("NB-004", "델 XPS 15",           "노트북", "정상",  "개발팀", date(2023, 3, 1),  "user-jisoo"),
        ("NB-005", "맥북 프로 13인치",   "노트북", "정상",  "제품팀", date(2023, 6, 1),  "user-dohyeon"),
        ("MN-001", "삼성 27인치 모니터", "모니터", "정상",  "영업팀", date(2022, 9, 1),  "user-minho"),
        ("MN-002", "LG 32인치 모니터",   "모니터", "미배정", None,    date(2024, 4, 1),  None),
        ("SV-001", "Dell PowerEdge R750", "서버",  "정상",  "개발팀", date(2021, 6, 1),  None),
    ]
```

- [ ] **Step 5: main()에 equipment 적재 추가**

`scripts/seed_business.py`의 `main()` 함수 안에서 `sales_rows` 선언 바로 아래에 추가:

```python
equipment_rows = build_equipment_rows()
```

그리고 `conn.execute("TRUNCATE business.sales RESTART IDENTITY")` 아래에 추가:

```python
await conn.execute("TRUNCATE business.equipment")
await conn.executemany(
    "INSERT INTO business.equipment "
    "(asset_id, name, category, status, assigned_dept, purchase_date, assigned_to) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7)",
    equipment_rows,
)
```

`print()` 메시지도 갱신:

```python
print(
    f"business 시드 완료: employees {len(employee_rows)}행, "
    f"sales {len(sales_rows)}행, equipment {len(equipment_rows)}행, "
    f"제한계정 sql_tool_ro(read-only)·sql_tool_rw(SELECT/UPDATE/DELETE)"
)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_business.py -v
```

예상: 전체 PASSED (기존 테스트 포함)

- [ ] **Step 7: 커밋**

```bash
cd backend && git add scripts/seed_business.py tests/scripts/test_seed_business.py
git commit -m "feat(seed): business.equipment 테이블 DDL + 시드 데이터 추가"
```

---

## Task 3: seed_fga.py — table:equipment FGA 튜플 추가

**Files:**
- Modify: `scripts/seed_fga.py`

- [ ] **Step 1: `_TABLE_GRANTS` 리스트에 equipment 튜플 추가**

`scripts/seed_fga.py`에서 `_TABLE_GRANTS` 리스트 안에 아래 2줄 추가 (기존 `table:sales` 항목들 아래):

```python
{"user": "role:c_level#member",      "relation": "dept_viewer", "object": "table:equipment"},
{"user": "department:개발팀#member", "relation": "dept_viewer", "object": "table:equipment"},
```

- [ ] **Step 2: seed_fga 테스트로 확인**

```bash
cd backend && .venv/bin/python -m pytest tests/scripts/test_seed_fga.py -v
```

예상: 기존 테스트 전체 PASSED (구조 변경 없음)

- [ ] **Step 3: 커밋**

```bash
cd backend && git add scripts/seed_fga.py
git commit -m "feat(fga): table:equipment dept_viewer 튜플 추가 (c_level + 개발팀)"
```

---

## Task 4: permission_validator.py + sql_tool.py — 상수 동기화

**Files:**
- Modify: `core/fga/permission_validator.py:22`
- Modify: `app/graph/tools/sql_tool.py:18`

- [ ] **Step 1: _KNOWN_TABLES에 equipment 추가**

`core/fga/permission_validator.py` 22번째 줄을 수정:

```python
_KNOWN_TABLES = {"employees", "sales", "equipment"}
```

- [ ] **Step 2: sql_tool _DESCRIPTION 갱신**

`app/graph/tools/sql_tool.py` 18~24번째 줄을 수정:

```python
_DESCRIPTION = (
    "사내 업무 DB(business.employees, business.sales, business.equipment)의 레코드를 조회·수정·삭제한다. "
    "직원의 사번·아이디(emp_id)·부서·직급·이메일·연봉, 매출 수치, 장비(자산) 현황 등 테이블 값을 묻는 조회뿐 아니라 "
    "'연봉을 바꿔줘', '장비를 지급해줘', '행을 삭제해줘' 같은 데이터 변경도 이 도구로 처리한다. "
    "특정 직원의 아이디/사번을 이름으로 찾는 것도 여기서 한다(감사 이력·권한 조회 도구가 아니다). "
    "권한 부여/회수가 아니라 '테이블 데이터' 작업일 때 쓴다. "
    "question 인자에 한국어 자연어 요청을 그대로 넣는다."
)
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/eval -q
```

예상: 기존 테스트 전체 PASSED

- [ ] **Step 4: 커밋**

```bash
cd backend && git add core/fga/permission_validator.py app/graph/tools/sql_tool.py
git commit -m "feat(validator): _KNOWN_TABLES + sql_tool 설명에 equipment 추가"
```

---

## Task 5: 근로계약서 문서 추가 (RAG 검색 대상)

**Files:**
- Create: `docs/company/legal/employment-contract-template.md`

- [ ] **Step 1: 문서 생성**

`docs/company/legal/employment-contract-template.md` 파일 생성:

```markdown
# 표준 근로계약서 양식

## 목적
TechCorp의 모든 정규직·계약직 입사자에게 적용하는 표준 근로계약서 양식이다.
법무팀이 관리하며, 변경 시 법무팀장 승인 필수.

## 계약 당사자
- **갑 (사용자)**: 주식회사 TechCorp, 대표이사 OOO
- **을 (근로자)**: 성명 ___________, 생년월일 ___________

## 주요 계약 조항

### 1. 근무 형태 및 장소
- 근무 형태: 정규직 / 계약직 (해당 항목에 표시)
- 근무 장소: TechCorp 본사 및 회사가 지정하는 장소

### 2. 업무 내용
- 담당 부서: ___________
- 직급: ___________
- 주요 업무: ___________

### 3. 근로 기간
- 정규직: 입사일로부터 정년까지
- 계약직: ___________ ~ ___________

### 4. 근무 시간
- 소정 근로시간: 주 40시간 (월~금, 09:00~18:00)
- 휴게 시간: 12:00~13:00 (1시간)
- 유연근무제 적용 대상 여부: 해당 부서 내규에 따름

### 5. 임금
- 연봉 총액: 별도 연봉 계약서에 명시
- 지급 방법: 매월 25일 지정 계좌 이체

### 6. 연차 유급휴가
- 1년 미만: 매월 1일 (최대 11일)
- 1년 이상: 근로기준법에 따른 연차

### 7. 사회보험
- 4대 보험(국민연금, 건강보험, 고용보험, 산재보험) 법령에 따라 적용

### 8. 비밀유지 의무
- 재직 중 및 퇴직 후 2년간 회사의 영업비밀·고객정보를 외부에 공개·유출 금지

### 9. 계약 해지
- 법령 및 취업규칙에 정한 사유 발생 시 계약 해지 가능
- 근로자 자발적 퇴직: 30일 전 사전 통보

## 서명란

| 구분 | 성명 | 서명 | 날짜 |
|------|------|------|------|
| 갑 (TechCorp 대표이사) | | | |
| 을 (근로자) | | | |

---
*본 양식은 법무팀이 관리합니다. 문의: legal@techcorp.example*
*최종 수정일: 2025-01-15 | 버전: v3.2*
```

- [ ] **Step 2: 문서가 인덱싱 대상 경로인지 확인**

```bash
cd backend && ls docs/company/legal/
```

예상: `contract-review.md`, `data-privacy.md`, `employment-contract-template.md`, `ip-policy.md`, `nda-policy.md`

- [ ] **Step 3: 커밋**

```bash
cd backend && git add docs/company/legal/employment-contract-template.md
git commit -m "docs(legal): 표준 근로계약서 양식 문서 추가 (데모 시나리오 장면 ②·⑥ 대상)"
```

---

## Task 6: 시드 스크립트 실행 및 전체 검증

- [ ] **Step 1: business 시드 실행**

```bash
cd backend && .venv/bin/python -m scripts.seed_business
```

예상:
```
business 시드 완료: employees 12행, sales 20행, equipment 8행, 제한계정 sql_tool_ro(read-only)·sql_tool_rw(SELECT/UPDATE/DELETE)
```

- [ ] **Step 2: FGA 시드 실행**

```bash
cd backend && .venv/bin/python -m scripts.seed_fga
```

예상: 오류 없이 완료 (멱등)

- [ ] **Step 3: 전체 테스트 실행**

```bash
cd backend && .venv/bin/python -m pytest tests/ --ignore=tests/eval -q
```

예상: 전체 PASSED, 0 failed

- [ ] **Step 4: 문서 재인덱싱 (벡터 DB)**

```bash
cd backend && .venv/bin/python -m scripts.index_docs
```

예상: `employment-contract-template.md` 포함 인덱싱 완료 메시지

- [ ] **Step 5: 최종 커밋**

```bash
cd backend && git add -A
git commit -m "chore(demo): equipment 시드 + FGA + legal 문서 통합 검증 완료"
```

---

## 데모 사전 체크리스트

장면별 동작 확인 (서버 기동 후 수동):

- [ ] 장면 ①: minjun 로그인 → "신입사원 온보딩 절차 알려줘" → RAG 응답 + `/company/hr` 출처 확인
- [ ] 장면 ②: minjun → "표준 근로계약서 양식도 보여줘" → 권한 없음 응답 확인
- [ ] 장면 ③: admin 로그인 → "현재 미배정 노트북 목록 보여줘" → NB-001, NB-002 포함 표 확인
- [ ] 장면 ④: admin → "이민준에게 NB-001 지급해줘" → HITL 팝업 → 승인 → 완료 확인
- [ ] 장면 ⑤: admin → "이민준에게 법무 문서 열람 권한 줘" → permission 도구 실행 확인
- [ ] 장면 ⑥: minjun → "표준 근로계약서 양식 보여줘" → 정상 응답 + `/company/legal` 출처 확인
