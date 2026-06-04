"""카탈로그 값 힌트 + drift 방지 테스트 (ADR-0021).

핵심 불변식 둘:
1. PII 컬럼은 값 힌트로 절대 노출되지 않는다(게이트 경계 보강).
2. 시드가 실제로 적재하는 카테고리형 값 ⊆ 카탈로그 허용값 — 시드에 새 값을 넣고
   카탈로그 갱신을 잊으면 이 테스트가 실패해 힌트 동기화를 강제한다.
"""
from pathlib import Path

import yaml

from core.sql import catalog
from scripts.seed_business import build_employee_rows, build_sales_rows, _DEPT_BASE_SALARY


def _users() -> list[dict]:
    return yaml.safe_load(Path("config/users.yaml").read_text())["users"]


# ── PII 불변식 ───────────────────────────────────────────────
def test_pii_columns_excluded_from_value_hints():
    text = catalog.value_hints_text()
    for pii_col in catalog.PII_COLUMNS:
        assert pii_col not in text
    # 대표적 PII 값 컬럼명이 힌트 라인에 등장하지 않는다.
    assert "salary" not in text and "email" not in text


def test_categorical_and_pii_are_disjoint():
    assert set(catalog.CATEGORICAL_VALUES).isdisjoint(catalog.PII_COLUMNS)


def test_value_hints_render_actual_stored_codes():
    text = catalog.value_hints_text()
    assert "business.employees.department" in text
    assert "개발팀" in text          # 영문 코드(한글 아님) — value mismatch 처방
    assert "business.sales.period" in text


# ── drift: 시드 산출값 ⊆ 카탈로그 ─────────────────────────────
def test_sales_seed_values_subset_of_catalog():
    rows = build_sales_rows()
    periods = {r[0] for r in rows}
    depts = {r[1] for r in rows}
    products = {r[2] for r in rows}
    assert periods <= set(catalog.SALES_PERIODS)
    assert depts <= set(catalog.SALES_DEPARTMENTS)
    assert products <= set(catalog.CATEGORICAL_VALUES["business.sales.product"])


def test_employee_seed_values_subset_of_catalog():
    rows = build_employee_rows(_users())
    depts = {r[2] for r in rows}
    positions = {r[3] for r in rows}
    assert depts <= set(catalog.DEPARTMENTS)
    assert positions <= set(catalog.POSITIONS)


def test_salary_base_departments_known_to_catalog():
    # 연봉 기준액 lookup 키도 카탈로그 부서 축 안에 있어야 한다.
    assert set(_DEPT_BASE_SALARY) <= set(catalog.DEPARTMENTS)
