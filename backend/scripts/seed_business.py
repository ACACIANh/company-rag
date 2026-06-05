"""가상 업무 DB 시드 (ADR-0020): app DB에 business 스키마 + read-only 제한계정.

신원×위험도 SQL 게이트(ADR-0016)의 자율 SQL 도구가 붙을 대상 DB.
- 스키마: business (운영 객체가 있는 public 스키마와 논리 분리)
- 테이블: business.employees(직원, salary·email = PII), business.sales(매출), business.equipment(자산 현황)
- 제한계정: sql_tool_ro — business 스키마 read-only만. public 스키마 접근 차단.
- 쓰기 제한계정: sql_tool_rw — business 스키마 SELECT/UPDATE/DELETE만. INSERT·DDL·public 차단 (ADR-0034).

멱등 실행: `cd backend && .venv/bin/python -m scripts.seed_business`
제한계정 비밀번호는 SQL_TOOL_RO_PASSWORD / SQL_TOOL_RW_PASSWORD 환경변수, 미설정 시 dev 기본값.
"""
import asyncio
import os
from datetime import date
from pathlib import Path

import asyncpg
import yaml

from core.config import load_config
from core.sql import catalog

# 부서별 연봉 기준액(원). index 가산으로 행마다 분산 → 결정론.
# 키는 카탈로그의 부서 축과 일치해야 한다(값 힌트 ↔ 시드 drift 방지, ADR-0021).
_DEPT_BASE_SALARY = {
    "임원": 180_000_000,
    "개발": 95_000_000,
    "제품": 90_000_000,
    "재무": 88_000_000,
    "영업": 82_000_000,
    "법무": 92_000_000,
    "인사": 78_000_000,
    "디자인": 80_000_000,
    "미배정": 70_000_000,
}

# 매출 시드 축 — 카탈로그(단일 출처)에서 가져온다 (ADR-0021).
_SALES_PERIODS = catalog.SALES_PERIODS
_SALES_DEPTS = catalog.SALES_DEPARTMENTS
_DEPT_PRODUCT = catalog.DEPT_PRODUCT


def _primary_department(user: dict) -> str:
    depts = user.get("departments") or []
    if depts:
        return depts[0]
    if "c_level" in (user.get("fga_roles") or []):
        return "임원"
    return "미배정"


def build_employee_rows(users: list[dict]) -> list[tuple]:
    """users.yaml → business.employees 행. salary/email은 결정론적 합성(PII 시연용)."""
    rows: list[tuple] = []
    for i, user in enumerate(users):
        dept = _primary_department(user)
        is_exec = "c_level" in (user.get("fga_roles") or [])
        is_lead = bool(user.get("dept_admin_of"))
        if is_exec:
            position = "CTO"
        elif is_lead:
            position = "팀장"
        else:
            position = "팀원"
        salary = _DEPT_BASE_SALARY.get(dept, _DEPT_BASE_SALARY["미배정"]) + i * 1_000_000
        hire_date = date(2018 + i % 7, 1 + i % 12, 1)
        email = user.get("email") or f"{user['username']}@techcorp.example"
        name = user.get("display_name") or user["username"]
        rows.append((user["user_id"], name, dept, position, hire_date, salary, email))
    return rows


def build_sales_rows() -> list[tuple]:
    """부서×분기 매출 행. 결정론적 합성(PII 아님)."""
    rows: list[tuple] = []
    for p, period in enumerate(_SALES_PERIODS):
        for d, dept in enumerate(_SALES_DEPTS):
            amount = 100_000_000 + (p + 1) * (d + 1) * 17_000_000
            rows.append((period, dept, _DEPT_PRODUCT[dept], amount))
    return rows


def build_equipment_rows() -> list[tuple]:
    """business.equipment 시드 행. 결정론적 합성. 미배정 노트북 2개 이상 보장."""
    rows = [
        # (asset_id, name, category, status, assigned_dept, purchase_date, assigned_to)
        ("NB-001", "맥북 프로 14인치",    "노트북", "미배정", None,     date(2024, 1, 10), None),
        ("NB-002", "맥북 에어 M3",         "노트북", "미배정", None,     date(2024, 3, 15), None),
        ("NB-003", "레노버 ThinkPad X1",  "노트북", "수리중", "인사", date(2022, 1, 15), None),
        ("NB-004", "델 XPS 15",            "노트북", "정상",  "개발", date(2023, 3,  1), "user-joohwan"),
        ("NB-005", "맥북 프로 13인치",    "노트북", "정상",  "제품", date(2023, 6,  1), "user-dohyeon"),
        ("MN-001", "삼성 27인치 모니터",  "모니터", "정상",  "영업", date(2022, 9,  1), "user-minho"),
        ("MN-002", "LG 32인치 모니터",    "모니터", "미배정", None,     date(2024, 4,  1), None),
        ("SV-001", "Dell PowerEdge R750", "서버",   "정상",  "개발", date(2021, 6,  1), None),
    ]
    valid_cats = set(catalog.EQUIPMENT_CATEGORIES)
    valid_stats = set(catalog.EQUIPMENT_STATUSES)
    for r in rows:
        assert r[2] in valid_cats,  f"equipment category drift: {r[2]!r}"
        assert r[3] in valid_stats, f"equipment status drift: {r[3]!r}"
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


def _grant_rw_sql(password: str) -> str:
    """쓰기 제한계정 생성 + 권한 (멱등). business 스키마 SELECT/UPDATE/DELETE만,
    INSERT·DDL·public 스키마는 미부여(ADR-0034 방어심층 2차)."""
    pw = password.replace("'", "''")
    return f"""
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sql_tool_rw') THEN
      CREATE ROLE sql_tool_rw LOGIN PASSWORD '{pw}';
   ELSE
      ALTER ROLE sql_tool_rw LOGIN PASSWORD '{pw}';
   END IF;
END
$$;

-- 운영 객체(public 스키마) 접근 차단
REVOKE ALL ON SCHEMA public FROM sql_tool_rw;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM sql_tool_rw;

-- business 스키마: 읽기 + UPDATE/DELETE만 (DDL 미부여, 쓰기는 UPDATE/DELETE로 제한)
GRANT USAGE ON SCHEMA business TO sql_tool_rw;
GRANT SELECT, UPDATE, DELETE ON ALL TABLES IN SCHEMA business TO sql_tool_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA business GRANT SELECT, UPDATE, DELETE ON TABLES TO sql_tool_rw;

-- 계정 레벨 방어: statement timeout (쓰기 계정이라 RO 트랜잭션은 설정하지 않음)
ALTER ROLE sql_tool_rw SET statement_timeout = '5s';
"""


async def main() -> None:
    cfg = load_config()
    password = os.getenv("SQL_TOOL_RO_PASSWORD", "sql_tool_ro_dev")
    rw_password = os.getenv("SQL_TOOL_RW_PASSWORD", "sql_tool_rw_dev")

    users = yaml.safe_load(Path("config/users.yaml").read_text())["users"]
    employee_rows = build_employee_rows(users)
    sales_rows = build_sales_rows()
    equipment_rows = build_equipment_rows()

    conn = await asyncpg.connect(cfg.postgres_dsn)
    try:
        await conn.execute(_DDL)
        # 멱등: 매번 비우고 다시 적재
        await conn.execute("TRUNCATE business.employees")
        await conn.execute("TRUNCATE business.sales RESTART IDENTITY")
        await conn.execute("TRUNCATE business.equipment")
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
        await conn.executemany(
            "INSERT INTO business.equipment "
            "(asset_id, name, category, status, assigned_dept, purchase_date, assigned_to) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            equipment_rows,
        )
        await conn.execute(_grant_sql(password))
        await conn.execute(_grant_rw_sql(rw_password))
    finally:
        await conn.close()

    print(
        f"business 시드 완료: employees {len(employee_rows)}행, "
        f"sales {len(sales_rows)}행, equipment {len(equipment_rows)}행, "
        f"제한계정 sql_tool_ro(read-only)·sql_tool_rw(SELECT/UPDATE/DELETE)"
    )


if __name__ == "__main__":
    asyncio.run(main())
