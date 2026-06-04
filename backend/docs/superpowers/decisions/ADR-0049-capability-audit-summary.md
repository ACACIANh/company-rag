# ADR-0049: capability 안내 감사 요약(capability audit summary)

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-05
**Context**: 최초 질문이 capability(권한 기능 안내) 라우트를 탈 때, 관리자는 안내와 함께 게이트 운영 현황(결정 건수)을 즉시 보고 싶다. 일반 사용자에게는 감사 로그가 전 사용자 민감정보라 노출하면 안 된다.

## Options
### 노출 대상
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 관리자(`justify_grant` on `capability:admin`)에게만 안내 본문 끝에 요약 첨부 | 권한 가진 사람만 운영 현황 확인. 민감정보 비노출. **채택** |
| B. 모든 사용자에게 노출 | 감사 로그는 전 사용자 민감정보 — 누수. 기각 |

### 형식
| 선택지 | 트레이드오프 |
|--------|------------|
| 건수 요약만(`count_by_decision`: ALLOW/DENY/JUSTIFY) | 한눈 파악. 상세는 기존 도구가 담당. **채택** |
| 상세 목록 첨부 | `query_audit_history`(ADR-0040)와 중복. 기각 |

## Decision
**선택: A(관리자 전용) + 건수 요약만**

1. **게이트**: `capability_node`가 `fga_client.check(user, justify_grant, capability:admin)`로 관리자 여부를 판정. 관리자가 아니면 일반 안내(`_TEXT_USER`)만 반환하고 요약을 붙이지 않는다.
2. **집계**: `AuditSink.count_by_decision()`(core/observability/audit/) 가 게이트 결정을 ALLOW/DENY/JUSTIFY로 센다(`JUSTIFY_AND_APPROVE`는 JUSTIFY로 축약 표시).
3. **첨부**: 관리자 안내(`_TEXT_ADMIN`) 끝에 `_format_audit_summary`로 "총 N건 (ALLOW · DENY · JUSTIFY)" 한 줄을 덧붙인다. `audit_sink`가 없으면 요약 생략(선택적 의존).
4. **total 일관화**: total은 표시 항목(ALLOW/DENY/JUSTIFY)의 합으로 계산해, 표시되지 않는 결정 종류가 있어도 "총합 = 보이는 항목 합"이 어긋나지 않게 한다.
5. **비목표**: 상세 목록·기간 필터·차트는 없음 — 상세 조회는 기존 `query_audit_history`(ADR-0040)가 제공한다.

## Rationale
- **관리자 전용**: 감사 로그는 전 사용자의 권한 시도 기록이라 민감하다. 권한 게이트를 운영하는 사람(=관리자)만 현황을 봐야 누수가 없다.
- **건수만**: capability 라우트는 "무엇을 할 수 있는지" 안내가 본질이다. 여기에 상세 목록까지 얹으면 이미 있는 `query_audit_history`와 중복되고 안내가 장황해진다. 한 줄 건수 요약이 "운영이 돌아가고 있다"는 신호로 충분하다.
- **total 표시 항목 합**: 사용자가 보는 숫자끼리 산수가 맞아야 신뢰가 간다.

## 관련
- [ADR-0018](ADR-0018-decision-audit-log.md) — 게이트 결정 감사 로그(본 요약의 데이터 출처)
- [ADR-0040](ADR-0040-audit-history-tool.md) — 상세 조회 도구 `query_audit_history`(중복 회피 대상)
- [ADR-0048](ADR-0048-tool-label-auto-discovery.md) — 같은 작업의 도구 라벨 자동 발견
