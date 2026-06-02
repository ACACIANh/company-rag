# ADR-0020: 신원×위험도 SQL 게이트의 전제 인프라

> **Status**: 🟢 적용완료

**Date**: 2026-06-02
**Context**: [ADR-0016](ADR-0016-identity-risk-sql-gate.md)(신원×위험도 게이트)·[ADR-0017](ADR-0017-sql-risk-classification.md)(위험도 분류)·[ADR-0018](ADR-0018-decision-audit-log.md)(감사 로그)는 각자 "미해결/후속(착수 전 전제)"로 공통 인프라를 가리킨다. 이들은 개별 ADR의 본문 결정이 아니라 **세 ADR이 공유하는 토대**이므로, 흩어진 전제를 하나의 결정으로 승격해 먼저 못 박는다.

본 ADR이 묶는 전제 3종:
- 가상 업무 DB(직원·매출 시드) + 실행 격리
- `AgentState` 확장(`generated_sql`/`sql_risk`/`gate_decision`)
- `sqlglot` 의존성 도입

> **체크포인터 전제 정정**: 당초 본 ADR은 ADR-0016이 "기존 자산"으로 전제한 `AsyncPostgresSaver`가 미배선이라 보고 "전환"을 전제 4종에 넣었으나, 실제로는 **이미 충족**되어 있다 — FastAPI lifespan(`app/api/chat.py`)이 `AsyncPostgresSaver.from_conn_string(...)` + `checkpointer.setup()`으로 주입하며, `app/graph/builder.py`의 `MemorySaver`는 checkpointer 미주입 시 fallback(테스트·스크립트 경량 경로)일 뿐이다. 따라서 ADR-0016의 "기존 자산" 전제는 유효하며, 본 ADR에 체크포인터 전환 작업은 없다.

## Options

### ① 가상 업무 DB 격리 수준

| 선택지 | 트레이드오프 |
|--------|------------|
| RAG 운영 DB에 업무 테이블 혼재 | 인프라 0. 그러나 SQL 도구가 문서청크·세션·FGA 캐시를 건드릴 수 있어 격리 원칙(ADR-0016) 위반 |
| 별도 Postgres 컨테이너(물리 분리) | 가장 강한 격리. 그러나 docker-compose·연결 풀·설정 신규, 포트폴리오 규모엔 과함 |
| **같은 인스턴스 `business` 스키마 + read-only 제한계정** | 기존 단일 Postgres 재사용. 스키마 네임스페이스로 논리 분리 + 계정 권한으로 쓰기/타 스키마 접근 차단 |

### ② 위험도 파서

[ADR-0017](ADR-0017-sql-risk-classification.md)에서 `sqlglot`(AST 확정 + LLM 보강)으로 이미 결정. 본 ADR은 그 **의존성 도입·버전 고정**을 전제 작업으로 흡수한다(별도 재논의 없음).

## Decision

**선택: 위 3종을 PR-1(전제 인프라)로 묶어 선행 구축한다.**

1. **가상 업무 DB**: 같은 Postgres 인스턴스에 `business` 스키마를 신설하고 직원·매출 등 시연용 시드를 적재한다. SQL 도구는 **read-only 권한만 가진 제한 계정**으로 `business` 스키마에만 접속하며, **read-only 트랜잭션 · statement timeout · row limit**으로 실행을 가둔다. RAG 운영 객체(문서청크·세션·FGA 캐시·체크포인트)에는 접근 권한 자체를 부여하지 않는다.
2. **`AgentState` 확장**: `generated_sql: str` / `sql_risk: str` / `gate_decision: str` 필드를 `AgentState(TypedDict)`에 추가한다(임의 dict 금지 — CLAUDE.md 규칙 2). 감사 레코드(ADR-0018)와 1:1 매핑되도록 명명한다.
3. **`sqlglot` 도입**: `pyproject.toml`에 `sqlglot`을 추가하고 Postgres 방언으로 고정한다(ADR-0017).

> 체크포인터(`AsyncPostgresSaver`)는 이미 `app/api/chat.py` lifespan에 배선되어 있어 본 PR의 작업 범위가 아니다(위 Context 정정 참조).

### 실행 격리 요약

```
앱(일반 계정)  ──> RAG 운영 객체 (문서청크·세션·FGA·checkpoint)   [SQL 도구 접근 불가]
SQL 도구       ──> business 스키마 (read-only 제한계정·RO 트랜잭션·timeout·row-limit)
```

## Rationale

- **전제를 결정으로 승격**: 세 ADR에 흩어진 "착수 전 전제"를 한 곳에서 못 박아, 0016 착수 시 빠진 토대로 인한 함정을 제거한다.
- **단일 Postgres 재사용**: 스키마 + 계정 권한 조합으로 신규 외부 의존 없이 논리 분리와 격리를 동시에 얻는다(ADR-0009의 "Redis 대신 Postgres" 기조와 일치). 물리 분리는 포트폴리오 규모에 과하다고 판단.
- **격리는 권한과 독립**: 게이트(ADR-0016)가 뚫려도 제한계정·read-only가 영향 범위를 `business` 스키마 읽기로 한정한다 — 방어 심층화.
- **resume 내구성은 이미 확보**: NEEDS_APPROVAL(현 명칭 `JUSTIFY_AND_APPROVE` — [ADR-0027](ADR-0027-justify-and-approve-self-service-gate.md))은 사람이 임의 시점에 승인하므로 그 사이 프로세스 재시작을 견뎌야 하는데, 프로덕션 경로의 체크포인트가 이미 `AsyncPostgresSaver`로 Postgres에 영속화되어 있어 이 전제는 충족 상태다.

## 미해결 / 후속

- `business` 시드 스키마 설계(직원·매출 외 테이블 범위)와 제한계정 권한 grant 스크립트 위치(`scripts/`).
- `AsyncPostgresSaver` 전환 시 기존 in-flight 체크포인트 호환성(현재 데모 단계라 마이그레이션 부담은 낮음).
- statement timeout·row limit 구체 수치는 PR-1 구현 시 확정.

## 영향받는 결정

- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 본 ADR이 그 "미해결/후속(전제)" 중 가상 업무 DB·`AgentState` 확장을 구축한다. AsyncPostgresSaver "기존 자산" 전제는 검증 결과 유효함을 확인했다(`app/api/chat.py` lifespan에 이미 배선).
- [ADR-0017](ADR-0017-sql-risk-classification.md) — `sqlglot` 의존성 도입을 본 ADR이 전제 작업으로 흡수한다.
- [ADR-0018](ADR-0018-decision-audit-log.md) — `AgentState`의 `gate_decision`/`sql_risk`를 감사 레코드와 1:1 매핑하도록 본 ADR에서 명명한다.
