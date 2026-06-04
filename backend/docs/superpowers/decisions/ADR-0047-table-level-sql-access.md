# ADR-0047: 테이블별 SQL 접근 권한

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-05
**Context**: SQL 게이트(ADR-0028)는 `capability:sql`의 **위험도 단위**(select/bulk_select/update_delete/ddl)로만 권한을 본다. 어느 **테이블**을 건드리는지는 구분하지 않아, `allow_select` 보유자는 급여 PII가 든 `business.employees`든 `business.sales`든 전부 조회할 수 있다. ADR-0021/0028이 "신원별로 조회 가능한 테이블 자체가 달라질 전망 — 별도 ADR로 분리"로 예고한 부분을 구현한다.

## Options
### 시행 지점
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 하드 게이트(실행 전 차단) | 생성 SQL의 참조 테이블을 파싱해 접근권 없으면 실행 전 DENY. 확실한 차단. **채택** |
| B. 프롬프트 필터링만 | 권한 없는 테이블을 프롬프트 카탈로그에서 숨겨 생성 자체를 막음. 강제력 없음(LLM 우회 가능) |
| C. 둘 다 | 가장 견고하나 구현량 큼. 필터링은 후속으로 |

### 권한 단위
| 선택지 | 트레이드오프 |
|--------|------------|
| 테이블 접근 여부만(`can_access`) | "이 테이블을 건드릴 수 있나"만 판정. 읽기/쓰기 구분은 기존 위험도 게이트가 담당(직교). **채택** |
| 테이블 × 읽기/쓰기 | 더 세밀하나 기존 위험도 게이트와 일부 중첩 — 경계 설계 부담. YAGNI |

## Decision
**선택: A(하드 게이트) + "테이블 접근 여부만"**

1. **모델**: `fga/model.fga`에 `type table` 신설(+`model.json` 동기). `define can_access: [user, department#member, role#member]`. 인스턴스: `table:employees`, `table:sales`.
2. **테이블 추출**: `core/sql/tables.py`의 `extract_tables(sql)` — sqlglot AST의 `exp.Table`에서 base 테이블 bare 이름을 모으고 CTE 별칭은 제외한다. 순수 함수(LangGraph 무관).
3. **하드 게이트(AND 결합)**: `tool_gate_node`에서 SQL 위험도 게이트가 ALLOW/JUSTIFY를 낸 뒤, 참조 테이블 각각에 `check(user:caller, can_access, table:<name>)`를 돈다. **하나라도 미보유면 최종 DENY로 강등**. 위험도 게이트(종류)와 테이블 게이트(대상)가 둘 다 통과해야 실행된다. 미부여 테이블·미지(unknown) 테이블은 `can_access` 튜플이 없어 자연히 DENY된다(보수적 차단). 참조 테이블이 없는 SQL(예: `SELECT 1`)은 통과.
4. **시드**: `scripts/seed_fga.py`에 `_TABLE_GRANTS` — c_level은 전 테이블, 부서는 업무 관련 테이블만(예: 인사팀·재무팀→`employees`, 영업팀·제품팀·재무팀→`sales`).
5. **비목표(YAGNI)**: 프롬프트 카탈로그 동적 필터링(시행 지점 B), 테이블×읽기/쓰기 세분화, 컬럼/행 단위 권한.

### 게이트 합성 위치
`gate_decision`(core.sql.gate)은 위험도 전용으로 유지하고, 테이블 게이트는 별도 함수 `gate_table_access(check, user_id, tables)`(core.sql.gate)로 둔다. SQL 문자열→테이블 추출은 `tool_gate_node`가 planned_action(=SQL)으로 호출해 두 게이트를 AND로 합성한다.

## Rationale
- **하드 게이트**: 프롬프트 필터링만으로는 LLM이 권한 밖 테이블을 생성할 여지가 남아 강제력이 없다. 실행 직전 AST로 참조 테이블을 확정해 차단하는 것이 PII 누수에 대한 확실한 방어선이다.
- **접근 여부만**: 읽기/쓰기 구분은 이미 위험도 게이트(`select` vs `update_delete`)가 담당한다. 테이블 게이트까지 읽기/쓰기로 쪼개면 두 축이 중첩돼 정책이 모호해진다. "어느 테이블이냐"와 "어떤 작업이냐"를 직교로 두고 AND 결합하는 것이 가장 단순하고 추론하기 쉽다.
- **미지 테이블 보수 차단**: `can_access` 튜플이 없는 테이블은 DENY가 기본값이라, 새 테이블 추가 시 시드를 빠뜨리면 열리는 게 아니라 닫히는(fail-closed) 방향이라 안전하다.

### 행동 변화(주의)
기존엔 `allow_select`(전원 부여)만으로 모든 테이블 SELECT가 가능했으나, 본 ADR 적용 후엔 **참조 테이블의 `can_access`도 보유해야** 한다. 시드(`_TABLE_GRANTS`)로 부서별 접근을 명시하지 않으면 해당 부서는 그 테이블을 조회할 수 없게 된다 — 의도된 강화다.

## 관련
- [ADR-0028](ADR-0028-capability-permission-model.md) — 위험도 capability 게이트(본 ADR과 AND 결합)
- [ADR-0021](ADR-0021-sql-schema-value-hints.md) — "테이블 접근권한 별도 ADR" 예고를 본 ADR이 해소
- [ADR-0017](ADR-0017-sql-risk-classification.md) — sqlglot AST 파서(테이블 추출에 재사용)
- [ADR-0046](ADR-0046-individual-grant-dept-admin-delegation.md) — 같은 PR의 권한 위임
