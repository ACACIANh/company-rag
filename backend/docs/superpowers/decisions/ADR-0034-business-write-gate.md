# ADR-0034: 게이트 통제 하 business 스키마 쓰기 허용(UPDATE/DELETE)

> **Status**: 🟢 적용완료

**Date**: 2026-06-04
**Context**: 수동 테스트에서 "직원 연봉 변경" 요청이 두 겹의 원인으로 거부됨. (A) 에이전트 LLM이 SQL 실행 대신 `manage_permission`으로 오라우팅(description 비대칭), (B) SQL 실행 계정 `sql_tool_ro`가 read-only라 UPDATE 자체가 불가(ADR-0020 방어심층). 게이트 통제 하에 `business` 스키마 UPDATE/DELETE를 허용하고, 이를 안전하게 실행할 이중 계정 구조를 도입한다.

## Options

### ① 쓰기 허용 범위

| 선택지 | 트레이드오프 |
|--------|------------|
| INSERT 포함 전 DML 허용 | 도구 단순. 그러나 INSERT는 업무 데이터 조작 시나리오에서 필요성이 낮고 공격 표면을 넓힘 |
| **UPDATE/DELETE만 허용(INSERT·DDL 제외)** | "연봉 변경·상태 수정" 시나리오 충족. INSERT·DDL은 게이트조차 없이 DENY → 최소 권한 |
| 현행 유지(쓰기 전부 DENY) | 변경 없음. 그러나 포트폴리오 데모 핵심 시나리오가 동작 안 함 |

### ② 실행 계정 구조

| 선택지 | 트레이드오프 |
|--------|------------|
| 단일 read-only 계정 유지, 쓰기 시도 시 DENY | 구조 단순. 그러나 게이트가 ALLOW/JUSTIFY를 반환해도 쓰기가 DB 수준에서 거부됨 |
| **이중 계정(sql_tool_ro / sql_tool_rw) + 위험도별 풀 선택** | SELECT → `sql_tool_ro` 풀, 게이트가 통과시킨 UPDATE/DELETE → `sql_tool_rw` 풀. 최소 권한 + 게이트 결정과 실행 계정을 1:1 연결 |
| 단일 read-write 계정으로 통합 | ADR-0020의 "격리는 권한과 독립" 원칙 붕괴. 게이트 우회 시 전 DML 노출 |

### ③ WHERE 없는 무조건 UPDATE/DELETE 처리

| 선택지 | 트레이드오프 |
|--------|------------|
| LLM 프롬프트 지시만으로 방어 | 비결정적. LLM이 실수로 WHERE 없는 쿼리를 생성할 가능성 있음 |
| **sqlglot AST risk 단계에서 DENY** | 파서 수준 확정 차단. 오탐(전체 테이블 의도) 가능성이 있으나 포트폴리오 범위에서는 정책상 수용 |

### ④ 도구 description 오라우팅 해소

| 선택지 | 트레이드오프 |
|--------|------------|
| 방치 | LLM이 "연봉 변경"을 계속 `manage_permission`으로 보낼 수 있음 |
| **sql_tool description에 데이터 값 변경 예시 추가, manage_permission에 SQL 실행 제외 명시** | description 정정으로 라우팅 정확도 향상. LLM이 비결정적이라 100% 보장은 아님 |

## Decision

**선택: ②(이중 계정) + ①(UPDATE/DELETE만) + ③(WHERE 가드) + ④(description 정정) 전부 채택.**

### 방어심층 3층 구조

```
1층 — 게이트 (core/sql/gate.py + OpenFGA)
      justify_update_delete@capability:sql
      → engineering 부서원 / c_level 역할만 JUSTIFY 통과
      → 통과 후 사람 승인(HITL interrupt) 필수

2층 — 쓰기 계정 분리 (app/graph/tools/sql_tool.py)
      SELECT 위험도       → sql_tool_ro 풀 (SELECT만, public 차단)
      UPDATE/DELETE 위험도 → sql_tool_rw 풀 (SELECT·UPDATE·DELETE만, public 차단)
      INSERT·DDL          → 계정 단계 이전에 게이트 DENY

3층 — WHERE 가드 (core/sql/risk.py)
      UPDATE/DELETE 문에 WHERE 절 없으면 sqlglot AST 파싱 → DENY
```

### 실행 격리 요약 (ADR-0020 보강)

```
SQL 도구(SELECT 경로)  ──> sql_tool_ro  ──> business 스키마 (읽기만)
SQL 도구(쓰기 경로)    ──> 게이트 JUSTIFY + HITL → sql_tool_rw ──> business 스키마 (SELECT·UPDATE·DELETE)
INSERT / DDL           ──> 게이트 DENY (rw 풀 도달 전에 차단)
RAG 운영 객체          ──> 양쪽 계정 모두 접근 불가 (ADR-0020 유지)
```

### 구현 위치

| 파일 | 변경 내용 |
|------|----------|
| `core/sql/risk.py` | WHERE 없는 UPDATE/DELETE → `RISK_UPDATE_DELETE` 분류 시 AST 검사, 없으면 DENY |
| `app/graph/tools/sql_tool.py` | `_ro_pool` / `_rw_pool` 이중 풀; 위험도에 따라 풀 선택; description에 데이터 값 변경 예시 추가 |
| `scripts/seed_business.py` | `sql_tool_rw` GRANT (SELECT·UPDATE·DELETE on `business.*`; public 차단) |
| `core/config.py` | `SQL_RW_DATABASE_URL` 설정 항목 추가 |
| `app/api/chat.py` | rw 풀 lifespan 초기화·주입 배선 |
| `app/graph/tools/manage_permission.py` | description에 "SQL 데이터 변경은 sql_tool 사용" 명시 |

## Rationale

- **이중 계정이 핵심**: 게이트가 JUSTIFY → HITL → resume 흐름을 통과해도, 실행 계정이 read-only면 DB가 오류를 낸다. 게이트 결정과 실행 계정을 동기화해야 HITL 의미가 있다.
- **ADR-0020 폐기 아님, 보강**: 스키마 격리·public 차단·statement timeout·row limit은 유효. 변경은 "실행 계정을 ro/rw로 이원화"뿐. ADR-0020의 "격리는 권한과 독립" 원칙이 rw 계정에도 적용된다(rw도 RAG 운영 객체 접근 없음).
- **INSERT·DDL 제외**: 포트폴리오 시나리오(연봉·상태 변경)는 UPDATE/DELETE로 충분. INSERT·DDL을 여는 것은 공격 표면 확대 대비 이득이 없다.
- **WHERE 가드**: LLM 생성 쿼리는 비결정적이라 프롬프트 지시만으로 `UPDATE employees SET salary=...`(WHERE 누락)를 완전히 막을 수 없다. AST 파싱 층을 추가해 실수로 전 행을 덮어쓰는 경우를 구조적으로 차단한다.
- **description 정정**: LLM이 "연봉 변경"을 `manage_permission`(권한 부여 도구)으로 보내는 것은 description이 비대칭이라서다. `sql_tool`에 데이터 값 변경 예시를, `manage_permission`에 SQL 실행 제외 명시를 추가해 라우팅 힌트를 강화한다. 100% 보장은 아니지만 오라우팅 빈도를 유의미하게 낮춘다.

## 미해결 / 후속

- **이력 표시 불일치**: HITL resume 완료 시 사유(justification)가 `user` 메시지로 체크포인트에 저장되어 대화 이력에 노출된다. 이는 별개 UX 이슈로, 본 ADR 범위 밖.
- **LLM 라우팅 비결정성**: description 정정이 라우팅 정확도를 높이지만 100% 보장 불가. 향후 도구 선택 eval 하니스로 정량 측정 필요(ADR-0029 부채 참조).
- **sql_tool_rw credential 관리**: 현재 `.env`에 `SQL_RW_DATABASE_URL`로 설정. 프로덕션에서는 시크릿 매니저 분리 검토 필요.
- **UPDATE/DELETE 롤백 시나리오**: `async with conn.transaction():` context manager 안에서 실행되므로 `Exception` 발생 시 asyncpg가 자동 롤백한다. 명시적 ROLLBACK 호출은 없으나 트랜잭션 범위가 보장됨 — 구현완료.

## 영향받는 결정

- [ADR-0020](ADR-0020-sql-gate-prerequisite-infra.md) — **보강(폐기 아님)**. 실행 계정이 단일 `sql_tool_ro`에서 ro/rw 이원화로 확장. "실행 격리 요약" 다이어그램이 ro/rw로 갱신됨. 스키마 격리·public 차단·timeout 등 나머지 전제는 그대로 유효.
- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 게이트 3-state(ALLOW/JUSTIFY/DENY) 위에 이중 계정 실행이 얹힘. 게이트 논리 무변경.
- [ADR-0027](ADR-0027-justify-and-approve-self-service-gate.md) — HITL JUSTIFY_AND_APPROVE 흐름 무변경. resume 이후 실행 계정 분기만 추가.
- [ADR-0028](ADR-0028-capability-permission-model.md) — `justify_update_delete@capability:sql` 튜플이 이 ADR의 게이트 1층을 제공. capability 모델 무변경.
