"""가상 업무 DB 시드 (ADR-0020): app DB에 business 스키마 + read-only 제한계정.

신원×위험도 SQL 게이트(ADR-0016)의 자율 SQL 도구가 붙을 대상 DB.
- 스키마: business (운영 객체가 있는 public 스키마와 논리 분리)
- 테이블: business.employees(직원, salary·email = PII), business.sales(매출)
- 제한계정: sql_tool_ro — business 스키마 read-only만. public 스키마 접근 차단.

멱등 실행: `cd backend && .venv/bin/python -m scripts.seed_business`
제한계정 비밀번호는 SQL_TOOL_RO_PASSWORD 환경변수, 미설정 시 dev 기본값.
"""
import asyncio
import os
from datetime import date
from pathlib import Path

import asyncpg
import yaml

from core.config import load_config

# 부서별 연봉 기준액(원). index 가산으로 행마다 분산 → 결정론.
_DEPT_BASE_SALARY = {
    "executive": 180_000_000,
    "engineering": 95_000_000,
    "product": 90_000_000,
    "finance": 88_000_000,
    "sales": 82_000_000,
    "legal": 92_000_000,
    "hr": 78_000_000,
    "design": 80_000_000,
    "unassigned": 70_000_000,
}

# 매출 시드 축
_SALES_PERIODS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]
_SALES_DEPTS = ["sales", "product", "engineering", "finance"]
_DEPT_PRODUCT = {
    "sales": "Enterprise License",
    "product": "SaaS Subscription",
    "engineering": "Platform API",
    "finance": "Advisory",
}


def _primary_department(user: dict) -> str:
    depts = user.get("departments") or []
    if depts:
        return depts[0]
    if "c_level" in (user.get("fga_roles") or []):
        return "executive"
    return "unassigned"


def build_employee_rows(users: list[dict]) -> list[tuple]:
    """users.yaml → business.employees 행. salary/email은 결정론적 합성(PII 시연용)."""
    rows: list[tuple] = []
    for i, user in enumerate(users):
        dept = _primary_department(user)
        is_exec = "c_level" in (user.get("fga_roles") or [])
        position = "CTO" if is_exec else "Member"
        salary = _DEPT_BASE_SALARY.get(dept, _DEPT_BASE_SALARY["unassigned"]) + i * 1_000_000
        hire_date = date(2018 + i % 7, 1 + i % 12, 1)
        email = f"{user['username']}@techcorp.example"
        rows.append((user["user_id"], user["username"], dept, position, hire_date, salary, email))
    return rows


def build_sales_rows() -> list[tuple]:
    """부서×분기 매출 행. 결정론적 합성(PII 아님)."""
    rows: list[tuple] = []
    for p, period in enumerate(_SALES_PERIODS):
        for d, dept in enumerate(_SALES_DEPTS):
            amount = 100_000_000 + (p + 1) * (d + 1) * 17_000_000
            rows.append((period, dept, _DEPT_PRODUCT[dept], amount))
    return rows


_DDL = """
CREATE SCHEMA IF NOT EXISTS business;

CREATE TABLE IF NOT EXISTS business.employees (
    emp_id      text PRIMARY KEY,
    name        text NOT NULL,
    department  text NOT NULL,
    position    text NOT NULL,
    hire_date   date NOT NULL,
    salary      integer NOT NULL,   -- PII
    email       text NOT NULL       -- PII
);

CREATE TABLE IF NOT EXISTS business.sales (
    sale_id     serial PRIMARY KEY,
    period      text NOT NULL,
    department  text NOT NULL,
    product     text NOT NULL,
    amount      bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _grant_sql(password: str) -> str:
    """read-only 제한계정 생성 + 격리 권한 (멱등). business만 SELECT, public 차단."""
    pw = password.replace("'", "''")
    return f"""
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sql_tool_ro') THEN
      CREATE ROLE sql_tool_ro LOGIN PASSWORD '{pw}';
   ELSE
      ALTER ROLE sql_tool_ro LOGIN PASSWORD '{pw}';
   END IF;
END
$$;

-- 운영 객체(문서청크·세션·FGA캐시·체크포인트 = public 스키마) 접근 차단
REVOKE ALL ON SCHEMA public FROM sql_tool_ro;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM sql_tool_ro;

-- business 스키마만 read-only
GRANT USAGE ON SCHEMA business TO sql_tool_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA business TO sql_tool_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA business GRANT SELECT ON TABLES TO sql_tool_ro;

-- 계정 레벨 심층 방어: 기본 read-only 트랜잭션 + statement timeout
ALTER ROLE sql_tool_ro SET default_transaction_read_only = on;
ALTER ROLE sql_tool_ro SET statement_timeout = '5s';
"""


async def main() -> None:
    cfg = load_config()
    password = os.getenv("SQL_TOOL_RO_PASSWORD", "sql_tool_ro_dev")

    users = yaml.safe_load(Path("config/users.yaml").read_text())["users"]
    employee_rows = build_employee_rows(users)
    sales_rows = build_sales_rows()

    conn = await asyncpg.connect(cfg.postgres_dsn)
    try:
        await conn.execute(_DDL)
        # 멱등: 매번 비우고 다시 적재
        await conn.execute("TRUNCATE business.employees")
        await conn.execute("TRUNCATE business.sales RESTART IDENTITY")
        await conn.executemany(
            "INSERT INTO business.employees "
            "(emp_id, name, department, position, hire_date, salary, email) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            employee_rows,
        )
        await conn.executemany(
            "INSERT INTO business.sales (period, department, product, amount) "
            "VALUES ($1, $2, $3, $4)",
            sales_rows,
        )
        await conn.execute(_grant_sql(password))
    finally:
        await conn.close()

    print(
        f"business 시드 완료: employees {len(employee_rows)}행, sales {len(sales_rows)}행, "
        f"제한계정 sql_tool_ro (business read-only)"
    )


if __name__ == "__main__":
    asyncio.run(main())
