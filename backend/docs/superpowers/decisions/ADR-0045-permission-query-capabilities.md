# ADR-0045: 권한 조회 스냅샷에 capability 권한 노출

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-04
**Context**: `manage_permission`의 권한 조회("내 권한 알려줘") 스냅샷이 OpenFGA 권한 중 일부(부서·역할·폴더)만 보여주고 `capability` 타입 권한(SQL 실행 등급·grant)을 누락한다. "모두 보여지게" 추가한다.

## 배경
`_format_permission_snapshot`은 `member`@`department`, `member`@`role`, `can_read`@`folder`만 노출했다. OpenFGA 모델(`fga/model.fga`)의 `capability` 타입 — `capability:sql`(select/bulk_select/update_delete/ddl), `capability:admin`(grant) — 은 조회 결과에 전혀 나타나지 않아, c_level 관리자조차 본인이 DB에서 무엇을 할 수 있는지 알 수 없었다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| **A. capability 해석형 추가** | 기존 부서·역할·폴더에 더해, 작업별 게이트 결정(즉시 허용/사유 기재 후 허용/불가)을 사람이 읽기 쉽게 표시. 실무 친화적. 게이트(`gate_decision`) 재사용 |
| B. capability 원시 relation 나열 | `justify_grant@capability:admin` 식 OpenFGA 표기 그대로. 모델 충실하나 해석 부담을 사용자에게 전가 |
| C. 전체 튜플 원시 덤프 | 문자 그대로의 "모두"지만 가독성 낮고, 부서/폴더 표기와 형식 불일치 |

## Decision
**선택: A — capability 해석형 추가**

- `_CAPABILITY_DISPLAY`: 표시 대상 작업 (SELECT / 대량 SELECT / UPDATE·DELETE / DDL / 권한 부여(grant))과 위험도 매핑. **표시 순서·라벨만** 둔다.
- `_resolve_capabilities(check, user_id)`: 각 위험도에 `core.sql.gate.gate_decision`을 호출해 `(라벨, 한국어 결정)` 목록 반환.
- `_DECISION_LABEL`: `ALLOW→"즉시 허용"`, `JUSTIFY_AND_APPROVE→"사유 기재 후 허용"`, `DENY→"불가"`.
- `execute()` query 분기가 기존 try 블록 안에서 capability를 조회해 `_format_permission_snapshot(...)`에 "SQL/관리 권한:" 섹션으로 렌더링.

## Rationale
- **게이트 매트릭스 단일 출처**: 위험도→capability 객체·relation 매핑과 3-state 판정은 이미 `gate_decision`에 있다(ADR-0028). 조회 표시를 위해 매트릭스를 복제하지 않고 그대로 재사용 — 게이트 정책이 바뀌면 조회 결과도 자동으로 따라간다.
- **레이어 경계 준수**: `permission_tool.py`(app)는 이미 `core.sql.gate`·`core.sql.risk`를 의존하므로 app→core 경계를 새로 위반하지 않는다.
- **사용자 선택**: AskUserQuestion에서 해석형(A)을 명시 선택. 원시 덤프(C)보다 실무 가독성 우선.

## 동작 변화
- 조회 경로가 capability 판정을 위해 추가 FGA `check`를 호출한다(위험도당 1~2회, 최대 ~9회). 기존 try/except가 감싸 실패 시 "권한 조회 오류" 반환.
- 자기 조회(caller == target)는 별도 admin 게이트를 두지 않지만, grant capability 판정 시 `justify_grant`@`capability:admin`을 1회 check한다(스냅샷 일부). 타인 조회의 admin 접근 게이트는 그대로 — 거부 시 capability 조회 전 early-return.

## 변경 파일
- `app/graph/tools/permission_tool.py`: `_CAPABILITY_DISPLAY`·`_DECISION_LABEL`·`_resolve_capabilities` 추가, `_format_permission_snapshot` 시그니처(+capabilities)·섹션 렌더링, `execute()` query 분기, import 보강
- `tests/app/graph/tools/test_permission_tool.py`: `_resolve_capabilities`/포매터 capability 단위 테스트 추가, 기존 self/admin 조회 테스트 갱신(capability check 반영)

## 검증
전체 523 passed. c_level 시드 권한 재현 렌더링이 사용자 승인 미리보기와 일치(SELECT 즉시 허용 / 대량·UPDATE·DELETE·grant 사유 기재 후 허용 / DDL 불가) 확인. eval 회귀는 검색 경로와 무관(도구 출력 포맷 변경)이라 영향 없음.
