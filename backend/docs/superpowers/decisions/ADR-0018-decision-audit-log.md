# ADR-0018: 게이트 결정·SQL 실행 감사 로그 인프라

> **Status**: 🟢 적용완료

**Date**: 2026-06-02
**Context**: [ADR-0016](ADR-0016-identity-risk-sql-gate.md)는 "모든 게이트 결정이 감사 로그에 남아 그대로 시연 자료가 된다"를 전제했으나, **현재 코드에 권한/실행 감사 로그 인프라가 없다**(`core/observability/`의 cost_tracker는 비용 추적 전용). 신원 × 위험도 게이트가 ALLOW/DENY/NEEDS_APPROVAL(현 명칭 `JUSTIFY_AND_APPROVE` — [ADR-0027](ADR-0027-justify-and-approve-self-service-gate.md)) 중 무엇을, 왜, 누구에게 내렸는지 사후에 재구성할 수 없으면 게이트의 신뢰성 주장 자체가 검증 불가다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| 별도 인프라 없이 앱 로그(stdout)에만 기록 | 비용 0. 그러나 질의 불가·유실·구조 없음 → "왜 차단됐나" 재구성 불가 |
| 외부 SIEM/관측 SaaS 연동 | 운영급. 그러나 포트폴리오 규모엔 과함, 신규 외부 의존 |
| **PostgreSQL 전용 감사 테이블 + append-only 기록** | 기존 단일 Postgres 재사용, 구조화·질의 가능. 스키마·기록 지점 신규 작성 필요 |

## Decision

**선택: PostgreSQL에 append-only 감사 테이블을 두고, 게이트 결정과 실행 결과를 기록한다.**

- 기록 시점: ① 위험도 분류 직후(등급·근거), ② 게이트 결정 직후(3-state·신원·매칭한 매트릭스 셀), ③ 실행/거부/승인-resume 결과.
- 기록 항목(출발점): `user_id`, 부서·역할 스냅샷, 원본 질문, 생성 SQL, `sql_risk`, `gate_decision`, 사유, 실행 결과 요약(또는 거부 대안), timestamp, checkpoint/thread id.
- **append-only**: UPDATE/DELETE 금지. 감사 로그 자신은 SQL 도구의 대상 DB에 두지 않는다(자기 위변조 방지).
- `core/observability/`의 기존 sink 패턴과 정합하는 인터페이스로 추가하되, cost_tracker와는 별개 테이블.

## Rationale

- **게이트의 방어력은 "재구성 가능성"에서 나온다**: 어떤 신원에 어떤 등급으로 무슨 결정을 why 내렸는지가 남아야 "같은 질문, 다른 결과"를 사후 입증할 수 있다.
- **단일 Postgres 재사용**: 신규 외부 의존 없이 구조화 질의를 얻는다(ADR-0009의 "Redis 대신 Postgres" 기조와 일치).
- **append-only + 대상 DB 분리**: 감사 대상(SQL 도구)이 감사 기록을 건드리지 못하게 해 무결성을 지킨다.

## 미해결 / 후속

- 보존 기간·PII 마스킹 정책(생성 SQL/결과에 PII가 실릴 수 있음).
- `AgentState`의 `gate_decision`/`sql_risk`(ADR-0016)와 감사 레코드의 1:1 매핑 확정.
- doc_search 경로(권한 pre-filter)의 결정도 같은 테이블에 남길지 — 본 ADR은 tool_call·SQL 게이트 범위로 한정, 확장은 후속.

## 영향받는 결정

- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 본 ADR이 그 "감사 로그 재사용" 전제를 "신규 구축"으로 정정·구체화한다.
