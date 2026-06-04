# ADR-0027: DBA 부재 가정 — `NEEDS_APPROVAL`을 `JUSTIFY_AND_APPROVE`(사유 기재 자가승인)로 개정

> **Status**: 🟢 적용완료 — 게이트 매트릭스·재명명·사유 기재 흐름 구현(feat/adr-0027-justify-and-approve). 쓰기 트랜잭션 격리는 ADR-0034(이중 계정 + asyncpg transaction) 로 해결. 사용자 노출 한국어 카피도 `confirm.py`에 적용완료.

**Date**: 2026-06-02
**Context**: [ADR-0016](ADR-0016-identity-risk-sql-gate.md)의 게이트는 회색지대를 `NEEDS_APPROVAL`로 두고 기존 `confirm_node`의 `interrupt()`/resume에 얹었다. 그러나 이 명칭은 **"별도 승인자(DBA·관리자)가 대기 중이며 그 사람의 결재를 기다린다"**는 조직 구조를 함의한다. 본 프로젝트의 전제는 정반대다 — **이 회사엔 DBA가 없고, 에이전트 자신이 DBA의 통제·감사 역할을 대신한다.** 외부 승인자가 없으므로 "승인 대기"는 영원히 풀리지 않는 상태이거나, 질문자가 곧 승인자인 자가승인이 되어 명칭과 실제가 어긋난다. 또한 ADR-0016 매트릭스는 c_level의 대량·PII 읽기를 무조건 `ALLOW`로 두는데, 최고 권한일수록 PII 접근의 **사유 기록**이 더 중요하다는 감사 관점과 충돌한다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| `NEEDS_APPROVAL` 명칭 유지, 자가승인으로 의미만 재해석 | 코드 변경 0. 그러나 명칭이 "외부 결재 대기"를 계속 함의해 독자·감사자를 오도, DBA 부재 전제와 모순 |
| 회색지대를 없애고 `ALLOW`/`DENY` 2-state로 단순화 | 게이트가 단순. 그러나 "사유를 남기고 통과"라는 자기책임·감사 추적 흐름이 사라져 DBA 대행 가치 소멸 |
| **`JUSTIFY_AND_APPROVE`로 재명명 + 사유 기재 의무화 + c_level PII도 사유 흐름** | 명칭이 실제 흐름(사유 기재 후 자가승인)과 일치, 모든 민감 접근에 감사 추적 강제. confirm_node의 resume 의미가 "승인 클릭"→"사유 입력"으로 바뀌어 검증 갱신 필요 |

## Decision

**선택: 회색지대 상태를 `NEEDS_APPROVAL` → `JUSTIFY_AND_APPROVE`로 재명명하고, 통과 조건을 "사유(reason) 기재"로 의무화한다. c_level의 대량·PII 읽기도 `ALLOW`가 아닌 `JUSTIFY_AND_APPROVE`로 둔다.**

전제 — **DBA 부재 → 에이전트가 DBA의 통제·감사 역할을 대행**한다. 외부 승인자가 없으므로 게이트의 회색지대는 "타인의 결재 대기"가 아니라 **"질문자 본인이 사유를 남기고 자기책임으로 통과(self-service)하며, 그 사유가 감사 로그에 영구 기록되는 흐름"**이다.

1. **재명명**: 게이트 3-state의 중간값 `NEEDS_APPROVAL` → `JUSTIFY_AND_APPROVE`. `core.sql.gate`의 `DECISION_*` 상수, `AgentState.gate_decision` 값, 감사 레코드 값 전반에 적용. (`ALLOW`/`DENY`는 불변.)
2. **사유 의무화**: `JUSTIFY_AND_APPROVE` 경로는 `confirm_node`의 `interrupt()`로 **사유 텍스트 입력을 요구**한다. resume 값은 더 이상 승인 여부(boolean)가 아니라 **사유 문자열**이다. 빈 사유/취소는 통과시키지 않는다(미기재 = 실행 안 함).
3. **사유 영구 기록**: 입력된 사유는 [ADR-0018](ADR-0018-decision-audit-log.md) 감사 테이블의 사유 컬럼에 신원·SQL·위험도·매칭 셀과 함께 append-only로 남긴다. 이 기록이 "DBA가 사후 추궁할 수 있는 근거"를 대신한다.
4. **c_level PII도 사유 흐름**: 대량·PII 읽기(`RISK_BULK_SELECT`)는 신원과 무관하게 `JUSTIFY_AND_APPROVE`로 통일한다 — c_level도 PII를 보려면 사유를 남겨야 한다. (기존 c_level=`ALLOW`에서 변경.)
5. **일반멤버 쓰기는 `DENY` 유지**: 일반멤버의 `UPDATE`/`DELETE`는 사유 기재로도 풀리지 않는다(이번 결정에서 변경 없음). 자기책임 흐름은 "읽기 회색지대"와 "engineering/c_level의 쓰기"에만 연다.

### 개정된 권한 매트릭스 (ADR-0016 매트릭스를 대체)

| SQL 위험도 | 일반멤버 (general) | engineering | c_level |
|-----------|:----------:|:-----------:|:-------:|
| `SELECT` (일반 읽기) | ALLOW | ALLOW | ALLOW |
| `BULK_SELECT` (대량·풀스캔·PII) | JUSTIFY_AND_APPROVE | JUSTIFY_AND_APPROVE | **JUSTIFY_AND_APPROVE** |
| `UPDATE` / `DELETE` | DENY | JUSTIFY_AND_APPROVE | JUSTIFY_AND_APPROVE |
| `DDL` (DROP / ALTER / CREATE / TRUNCATE) | DENY | DENY | DENY |
| 폴백 (파싱 실패·미지원·모호) | DENY | DENY | DENY |

> 변경점: ① 모든 `NEEDS_APPROVAL` → `JUSTIFY_AND_APPROVE`, ② c_level의 `BULK_SELECT`가 `ALLOW` → `JUSTIFY_AND_APPROVE`. 나머지 셀(특히 일반멤버 쓰기=DENY, 전 계층 DDL=DENY)은 불변.

## Rationale

- **명칭이 곧 위협 모델이다**: `NEEDS_APPROVAL`은 "조직에 승인자가 있다"를 함의한다. DBA가 없는 조직에선 거짓 함의이고, 게이트를 읽는 사람을 오도한다. `JUSTIFY_AND_APPROVE`는 "스스로 사유를 대고(justify) 자기 권한으로 통과(approve)한다"는 실제 흐름을 그대로 드러낸다.
- **사유 기재가 DBA 대행의 핵심**: DBA의 본질적 통제력은 "막는 권한"이 아니라 **"누가 왜 했는지 추궁할 수 있음"**이다. 사유를 강제 기록하면 자동화된 self-service여도 사후 감사·책임 추적이 성립한다.
- **최고 권한일수록 더 기록한다**: c_level의 PII 접근을 무조건 `ALLOW`로 두면 가장 민감한 접근이 가장 흔적 없이 일어난다. 사유 흐름으로 통일해 "권한이 높을수록 면제"가 아니라 "권한이 높아도 기록"으로 뒤집는다.
- **HITL 인프라 재사용은 유지**: 여전히 `confirm_node`의 `interrupt()`/AsyncPostgresSaver resume를 쓴다. 바뀌는 것은 resume 페이로드의 의미(승인 boolean → 사유 문자열)뿐이라 신규 인프라 비용이 없다.
- **일반멤버 쓰기 DENY 보존**: 자기책임 흐름을 쓰기까지 일반멤버에게 열면 "사유만 적으면 누구나 DELETE" 가 되어 위험 범위가 과도하게 넓어진다. 회색지대 완화는 읽기와 상위 신원의 쓰기로 한정한다.

## 미해결 / 후속 (구현 범위)

- **`core/sql/gate.py`**: `DECISION_NEEDS_APPROVAL` 상수·`_MATRIX` 값 치환, c_level `RISK_BULK_SELECT` 셀을 `JUSTIFY_AND_APPROVE`로 변경. (순수 정책 로직 — 단위 테스트 `tests/core/sql/test_gate.py` 동반 갱신.)
- **`app/graph/state.py`**: `gate_decision` 허용값 갱신, 사유를 담을 필드 필요 여부 검토(`AgentState` TypedDict 확장만, 임의 dict 금지 — CLAUDE.md 규칙 2).
- **`app/graph/nodes/confirm.py` / `edges.py`**: `interrupt()` 프롬프트를 "사유 입력"으로, resume 처리를 boolean → 사유 문자열로 변경. 빈 사유 가드.
- **감사 로그([ADR-0018](ADR-0018-decision-audit-log.md))**: 사유 컬럼에 입력 사유 기록(스키마는 이미 사유 항목 포함 — 값 의미만 확정). 결정값 문자열 마이그레이션 영향 확인.
- ~~(보류) 쓰기 실행 트랜잭션 충돌~~ → **해결 (ADR-0034)**: `sql_tool_rw` 계정 + `async with conn.transaction():`으로 쓰기 격리 완료. 실행 오류 시 asyncpg 자동 롤백. DDL은 전 계층 DENY 유지.
- **회귀**: 게이트 매트릭스 회귀 테스트, `tests/eval/runner.py` 점수 확인(DoD 2).
- ~~사용자 노출 문구 한국어 카피 확정~~ → **적용완료**: `confirm.py` — "다음 작업은 사유 기재 후 본인 책임으로 실행됩니다. 실행 사유를 입력하세요."

## 영향받는 결정

- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 본 ADR이 그 권한 매트릭스와 `NEEDS_APPROVAL` 명칭을 개정한다(3-state 게이트 구조 자체는 유지).
- [ADR-0017](ADR-0017-sql-risk-classification.md) — 위험도 등급 정의는 불변. 본 ADR은 등급→결정 매핑만 바꾼다.
- [ADR-0018](ADR-0018-decision-audit-log.md) — 사유 기재가 의무화되어 감사 레코드의 사유 컬럼이 "선택적 메모"에서 "통과 전제 입력"으로 격상된다.
- `project_next_agentic_tools` — tool_call 자율 도구 루프의 SQL 게이트 정책 개정.
