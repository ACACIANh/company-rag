"""업무 DB 조회 표면 카탈로그 (ADR-0021) — 순수 데이터, LangGraph 무관.

NL→SQL 생성의 value mismatch(예: "엔지니어링" → DB는 `engineering`) 버그를 막기
위해, 카테고리형 컬럼의 허용값을 한 곳에 선언한다. 시드(`scripts.seed_business`)와
생성 프롬프트가 이 단일 출처를 함께 소비하므로 둘 사이의 drift가 구조적으로 차단된다.

PII 불변식: PII 컬럼(name·salary·email)은 스키마에는 남기되 **값 힌트는 절대 생성하지
않는다**. 행 내용 노출은 게이트(ADR-0016)·FGA가 돌기 전 PII 누수가 되므로, 힌트는
비-PII·저카디널리티 카테고리형 컬럼으로만 한정한다.
"""

# ── 카테고리형 축 (시드와 프롬프트가 공유하는 단일 출처) ──────────────
# 부서 코드 — employees.department / sales.department 가 공유한다.
DEPARTMENTS = [
    "executive",
    "engineering",
    "product",
    "finance",
    "sales",
    "legal",
    "hr",
    "design",
    "unassigned",
]

# 직급 리터럴
POSITIONS = ["CTO", "Member"]

# 매출 분기
SALES_PERIODS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]

# 매출이 잡히는 부서(부서 코드의 부분집합)
SALES_DEPARTMENTS = ["sales", "product", "engineering", "finance"]

# 부서 → 제품 (sales.product)
DEPT_PRODUCT = {
    "sales": "Enterprise License",
    "product": "SaaS Subscription",
    "engineering": "Platform API",
    "finance": "Advisory",
}

# ── 컬럼 분류 ────────────────────────────────────────────────────────
# 값 힌트로 프롬프트에 노출할 카테고리형 컬럼 → 허용값.
CATEGORICAL_VALUES = {
    "business.employees.department": DEPARTMENTS,
    "business.employees.position": POSITIONS,
    "business.sales.period": SALES_PERIODS,
    "business.sales.department": SALES_DEPARTMENTS,
    "business.sales.product": sorted(set(DEPT_PRODUCT.values())),
}

# PII 컬럼 — 스키마엔 있으나 값 힌트 절대 금지(ADR-0016 게이트 경계 보강).
PII_COLUMNS = {
    "business.employees.name",
    "business.employees.salary",
    "business.employees.email",
}


def value_hints_text() -> str:
    """카테고리형 컬럼 허용값을 생성 프롬프트용 텍스트로 렌더링.

    PII 컬럼은 절대 포함하지 않는다(불변식). 새 카테고리형 컬럼을 PII로 잘못 넣으면
    여기서 즉시 깨지도록 단언으로 못 박는다.
    """
    lines = []
    for col, values in CATEGORICAL_VALUES.items():
        assert col not in PII_COLUMNS, f"PII 컬럼은 값 힌트로 노출 금지: {col}"
        joined = ", ".join(values)
        lines.append(f"- {col} ∈ [{joined}]")
    return "\n".join(lines)
