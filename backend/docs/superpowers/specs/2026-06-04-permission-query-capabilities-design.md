# 권한 조회에 capability 권한 노출 — 설계

> **Status**: ⚪ 제안됨 · 작성일 2026-06-04

## 배경 / 문제

`manage_permission` 도구의 권한 조회("내 권한 알려줘")가 반환하는 스냅샷
(`_format_permission_snapshot`)은 OpenFGA에 저장된 권한 중 일부만 보여준다.

- 노출 중: 소속 부서(`member`@`department`), 역할(`member`@`role`), 접근 가능 폴더(`can_read`@`folder`)
- **누락**: `capability` 타입 권한 — SQL 실행 등급(`capability:sql`의 select/bulk_select/update_delete/ddl)과 권한 부여(`capability:admin`의 grant)

c_level 관리자가 본인 권한을 조회해도 "DB에서 무엇을 할 수 있는지"가 보이지 않는다.
사용자 요청: "OpenFGA 권한 모두 보여지게".

## 결정 (사용자 승인)

권한 조회 스냅샷에 **capability 권한을 해석형(사람이 읽기 쉬운 등급)으로** 추가한다.
원시 튜플 덤프나 raw relation 나열이 아니라, 각 작업이 어떤 게이트 결정을 받는지를 보여준다.

## 범위

- 변경 파일: `app/graph/tools/permission_tool.py` (사실상 단일 파일)
- 테스트: `tests/app/graph/tools/test_permission_tool.py`
- 비범위: FGA 모델 변경 없음, 새 의존성 없음, 폴더/부서/역할 표기 변경 없음

## 설계

### 매트릭스 재사용 (단일 출처)
등급 판정 로직은 이미 `core/sql/gate.py`의 `gate_decision(check, user_id, risk)`에 있다
(위험도 → capability 객체·relation 매핑 + ALLOW / JUSTIFY_AND_APPROVE / DENY 3-state).
이를 **재사용**한다 — 매트릭스를 복제하지 않는다. `permission_tool.py`는 이미
`core.sql.gate`·`core.sql.risk`를 import하므로 레이어 경계(app→core)를 위반하지 않는다.

### 구성 요소 (모두 `permission_tool.py`)

1. **표시 목록 상수** — 사용자 승인 순서/라벨:
   `(SELECT, RISK_SELECT)` · `(대량 SELECT, RISK_BULK_SELECT)` ·
   `(UPDATE/DELETE, RISK_UPDATE_DELETE)` · `(DDL, RISK_DDL)` · `(권한 부여(grant), RISK_GRANT)`
2. **결정 → 한국어 라벨 맵**:
   `ALLOW → "즉시 허용"`, `JUSTIFY_AND_APPROVE → "사유 기재 후 허용"`, `DENY → "불가"`
3. **`_resolve_capabilities(check, user_id)`** 헬퍼: 각 위험도에 `gate_decision` 호출,
   `[(라벨, 결정라벨)]` 반환
4. **`execute()` query 분기**: 기존 try 블록 안에서 departments/roles/folders 조회 뒤
   `capabilities = await _resolve_capabilities(self._fga.check, target)` 추가 → 포매터 전달
5. **`_format_permission_snapshot(...)`** 에 `capabilities` 인자 추가, "SQL/관리 권한:" 섹션 렌더링

### 출력 예 (c_level admin)
```
사용자: user-admin
소속 부서: (없음)
역할(role): c_level
접근 가능 폴더 10개:
  - /company
  ...
SQL/관리 권한:
  - SELECT: 즉시 허용
  - 대량 SELECT: 사유 기재 후 허용
  - UPDATE/DELETE: 사유 기재 후 허용
  - DDL: 불가
  - 권한 부여(grant): 사유 기재 후 허용
```

## 동작 변화 (주의)

- 조회 경로가 capability 판정을 위해 추가 FGA `check`를 호출한다(위험도당 1~2회, 최대 ~9회).
  기존 try/except가 감싸 실패 시 "권한 조회 오류" 반환.
- 타인 조회의 admin 게이트는 그대로 — 거부 시 capability 조회 전에 early-return.
- 자기 조회(caller == target)는 admin 게이트를 건너뛰지만, capability 판정 시
  grant capability(`justify_grant`@`capability:admin`)를 1회 check한다(스냅샷 일부).

## 테스트

- **신규**: `_resolve_capabilities`/포매터 capability 섹션 — relation→bool side_effect로
  ALLOW / JUSTIFY / DENY 3종이 올바른 한국어 라벨로 렌더링되는지 검증
- **수정**: `test_execute_query_self_returns_snapshot` — `fga.check`를 AsyncMock으로 구성,
  `assert_not_called()` 제거(자기 조회도 capability check 발생), "SQL/관리 권한" 포함 검증
- **수정**: `test_execute_query_other_as_admin_succeeds` — `assert_awaited_once_with` →
  `assert_any_await`(capability check 추가로 호출 횟수 증가)

## DoD

1. 단위 테스트 추가/수정
2. eval 회귀: 이 변경은 도구 출력 포맷일 뿐 검색 경로와 무관 → 점수 영향 없음(명시)
3. ADR-0045 작성 + `python -m scripts.gen_adr_index` 로 인덱스 재생성
