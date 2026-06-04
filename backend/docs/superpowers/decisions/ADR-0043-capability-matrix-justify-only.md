# ADR-0043: capability 매트릭스 정리 — SELECT만 즉시허용, 그 외 위험군은 justify-only

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-04
**Context**: 위험군 capability에서 '무사유 즉시허용(allow_*)' 경로를 제거하고, 단순 SELECT만 ALLOW 유지. 그 외 모든 위험군(BULK_SELECT·UPDATE/DELETE·DDL·GRANT)은 사유 기재(JUSTIFY_AND_APPROVE) 전용으로 통일한다.

## 배경 — 두 가지 결함이 같은 뿌리

1. **admin 타인 권한 조회 불능**: `manage_permission`의 타인 조회 경로가 `check(user, "member", "capability:admin")`로 admin을 확인했으나, `capability` 타입엔 `member` relation이 없어 OpenFGA가 validation 에러 → 항상 "권한 없음"이 떴다. 기능 추가(PR #67) 이래 실제로 한 번도 동작한 적 없음(단위 테스트는 FGA를 모킹해 가림).
2. **capability_node admin 도움말 미표시**: 노드가 `allow_grant`를 체크하는데, 시드는 admin에게 `justify_grant`만 부여(ADR-0029, "grant는 항상 사유 기재"로 `allow_grant`를 의도적으로 비움). → admin도 일반 사용자 도움말을 받음.

둘 다 "코드가 모델에 존재하지 않거나 시드되지 않는 relation을 체크"한 같은 부류다. `allow_grant`/`allow_bulk_select`/`allow_ddl`은 모델에 정의만 되고 누구에게도 부여되지 않는 **죽은 relation**이었다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. admin 체크만 `justify_grant`로 수정 | 최소 변경. 그러나 죽은 `allow_*` relation이 남아 같은 버그가 재발할 여지 + 매트릭스 불일치 유지 |
| B. allow_grant만 제거 | grant 한정 정리. bulk_select·ddl의 죽은 allow_*는 잔존(향후 읽기 등급화 여지 보존) |
| **C. 매트릭스 일관 정리** | 미사용 위험군 `allow_*`(grant·bulk_select·ddl) 모두 제거. 단순 SELECT만 ALLOW, 그 외 전부 justify-only. 모델·게이트·검증기·프롬프트·시드 주석 일괄 정합. 향후 위험군 무사유 허용 경로 자체가 사라짐 |

## Decision
**선택: C — capability 매트릭스 일관 정리**

정리된 매트릭스:

| 위험 등급 | 유지 relation | 즉시허용(ALLOW) | 기본 시드 결과 |
|---|---|---|---|
| SELECT | `allow_select`, `justify_select` | ✅ | 전원 ALLOW |
| BULK_SELECT | `justify_bulk_select` | ❌ justify-only | 전원 JUSTIFY |
| UPDATE/DELETE | `justify_update_delete` | ❌ justify-only | 개발팀·c_level JUSTIFY, 그 외 DENY |
| DDL | `justify_ddl` | ❌ justify-only | 전원 DENY(미시드) |
| GRANT(권한관리) | `justify_grant` | ❌ justify-only | c_level·admin JUSTIFY, 그 외 DENY |

제거: `allow_bulk_select`, `allow_ddl`, `allow_grant` (모델 relation 자체). `allow_update_delete`는 선행 작업에서 이미 제거됨.

## Rationale
- **고위험일수록 기록(ADR-0027/0028 철학)의 일관 적용**: "모든 위험군 행위는 이력으로 남는 게 맞다." 사용자가 사유를 남기고 자기책임으로 통과하는 JUSTIFY 흐름만이 위험군의 유일한 통로가 된다. 단순 SELECT(읽기 baseline)만 예외로 즉시 허용.
- **모델에서 relation 제거 = 권한 부여 자체를 봉쇄**: 어떤 관리자도 `manage_permission`으로 위험군 '무사유 허용'을 grant할 수 없다(`_CAPABILITY_RELATIONS` 화이트리스트에서도 제외). 정책이 코드 분기가 아니라 모델 구조로 강제된다.
- **정합성 가드 추가**: gate는 justify-only 위험군에 대해 `allow_*` Check를 건너뛴다(없는 relation Check 시 OpenFGA 에러). 단위 테스트(`test_justify_only_risks_never_check_allow`)로 "위험군은 allow_*를 조회하지 않음"을 고정해, 모킹이 가렸던 부류의 버그를 막는다.
- ADR-0028의 allow/justify 2층 개념을 폐기하지 않고 **SELECT에 한정**해 유지한다(refines ADR-0028).

## 변경 파일
- `fga/model.fga`, `fga/model.json`: `allow_bulk_select`/`allow_ddl`/`allow_grant` 제거
- `core/sql/gate.py`: `_JUSTIFY_ONLY_RISKS`에 BULK_SELECT·DDL·GRANT 추가(SELECT만 allow 경로 유지)
- `core/fga/permission_validator.py`: `_CAPABILITY_RELATIONS`에서 제거 relation 삭제
- `app/graph/prompts.py`: 파싱 프롬프트 relation 목록 동기화
- `app/graph/nodes/capability_node.py`: admin 분기 `allow_grant`→`justify_grant`
- `app/graph/tools/permission_tool.py`: admin 조회 체크 `member`→`justify_grant`
- 테스트: gate 정합성 가드, validator 거부, capability_node, permission_tool 갱신
- `scripts/seed_fga.py`: 주석 정정(시드 튜플 변경 없음 — 제거 relation은 애초에 미시드)

## 배포 메모
모델(`model.json`)은 OpenFGA store에 업로드되어야 적용된다 — 배포 시 `scripts/fga_init.sh` 재실행 필요. 시드 튜플은 변경 없음.
