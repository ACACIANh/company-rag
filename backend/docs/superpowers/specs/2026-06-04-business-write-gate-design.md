# 설계: 게이트 통제 하 business 스키마 쓰기 허용 (UPDATE/DELETE)

**Date**: 2026-06-04
**Status**: 설계 승인됨 (구현 전)
**관련 ADR**: ADR-0016(신원×위험도 게이트)·ADR-0017(위험도 분류)·ADR-0020(전제 인프라·read-only)·ADR-0027(JUSTIFY self-service)·ADR-0028(capability 모델). 본 설계의 결정은 신규 **ADR-0034**로 기록한다.

## 배경 / 문제

수동 테스트에서 alice(engineering)로 "id 5 직원의 연봉을 7000만원으로 바꿔줘"를 시도하면 권한 거부가 발생했다. `gate_audit_log` 추적 결과 두 겹의 원인이 드러났다.

- **이슈 A (도구 오라우팅)**: 에이전트 LLM이 "연봉을 바꿔줘"(데이터 UPDATE 의도)를 `query_business_data`(SQL 도구)가 아니라 `manage_permission`(권한 관리 도구)으로 호출. permission_tool이 파싱 검증에 실패해 `RISK_DENY` 반환 → 게이트 DENY. admin도 동일 재현(권한 무관, LLM 도구 선택 문제). 원인은 두 도구 description의 비대칭 — SQL 도구가 "조회"만 표방하고 변경(write)을 언급하지 않음.
- **이슈 B (read-only 제약)**: SQL 실행 계정 `sql_tool_ro`가 business 테이블에 `SELECT`만 보유(ADR-0020의 의도적 2차 방어선). 이슈 A를 고쳐 UPDATE SQL을 생성·게이트 통과시켜도 execute 단계에서 권한 부족으로 실패한다. 즉 현재 아키텍처에서 데이터 변경은 불가능하다.

결정: 게이트 통제 하에 business 스키마에 한해 쓰기(UPDATE/DELETE)를 허용하되, ADR-0020의 방어심층 정신을 보존한다.

## 결정 요약

| 항목 | 결정 |
|------|------|
| 쓰기 범위 | **UPDATE + DELETE** (INSERT·DDL 제외) |
| 실행 계정 | **이중 계정/풀** — SELECT는 read-only, update_delete 통과분만 write 계정 |
| 가드레일 | **WHERE 필수** — 무조건 UPDATE/DELETE는 risk 단계에서 DENY |
| 부수 수정 | **도구 description** 정정으로 오라우팅(이슈 A) 해소 |

## 컴포넌트별 설계

### 1. DB 계층 — 쓰기 제한계정 `sql_tool_rw`

`scripts/seed_business.py`에 신규 제한계정을 추가한다.

- `business` 스키마에 **SELECT + UPDATE + DELETE**만 grant. **INSERT·DDL·타 스키마 접근은 부여하지 않는다.**
- RAG 운영 객체(문서청크·세션·FGA 캐시·checkpoint)에는 권한 자체를 부여하지 않는다 — ADR-0020의 스키마 격리 유지.
- 비밀번호는 `SQL_TOOL_RW_PASSWORD` 환경변수, 미설정 시 dev 기본값(기존 `sql_tool_ro` 패턴과 동일).
- `.env`에 `SQL_TOOL_RW_DSN` 추가. `core/config.py`에 `sql_tool_rw_dsn` 필드, `app/api/chat.py` lifespan에서 풀 생성·주입.

기존 `sql_tool_ro`는 SELECT 전용으로 그대로 유지(변경 없음).

### 2. risk.py — WHERE 가드 (결정론적)

`core/sql/risk.py`의 `_classify_statement`에서 `exp.Update`/`exp.Delete` 노드에 WHERE 절(`stmt.args.get("where")`)이 없으면 `RISK_DENY`를 반환한다. sqlglot AST 기반이라 LLM에 의존하지 않는다.

- WHERE 있는 UPDATE/DELETE → `RISK_UPDATE_DELETE` (기존 동작)
- WHERE 없는 UPDATE/DELETE → `RISK_DENY` (신규 가드)
- 서브쿼리/CTE 등 다중 statement는 기존 승급 로직 유지. write 노드가 하나라도 WHERE 없으면 보수적으로 DENY.

### 3. SqlToolHandler — 이중 풀 라우팅

`app/graph/tools/sql_tool.py`:

- 생성자에 `ro_pool`(기존 `sql_pool` 역할)과 `rw_pool`(신규)을 주입.
- `execute(planned_action, risk)`로 시그니처 확장: `risk == RISK_UPDATE_DELETE`면 `rw_pool`, 그 외(`select`/`bulk_select`)는 `ro_pool` 사용.
- SELECT 경로는 기존대로 `fetch` + `_format_rows`.
- UPDATE/DELETE 경로는 트랜잭션으로 감싸 `execute`하고 **영향 행 수**를 결과 문자열로 반환(예: `"3개 행이 변경되었습니다."`). 예외는 기존처럼 `"SQL 실행 오류: {타입}"`로 닫는다.

`risk`는 이미 게이트 경로에 존재한다: ALLOW 경로의 `tool_gate_node`가 `risk` 변수를 보유하고(tool_gate.py:59), JUSTIFY 경로는 `pending_tool_calls`에 `risk`를 저장(tool_gate.py:64)해 `justify_execute`가 `p["risk"]`로 읽는다(justify_execute.py:21·30). 따라서 호출부 두 곳(`tool_gate_node`, `justify_execute`)이 `handler.execute(planned_action, risk)`로 인자만 추가하면 된다 — 신규 전달 경로 불필요.

핸들러 `execute` 인터페이스는 `(planned_action, risk)`로 통일한다(`app/graph/tools/base.py`의 프로토콜 갱신). `permission_tool`은 풀 분기가 없어 `risk` 인자를 받기만 하고 사용하지 않는다 — 호출부가 핸들러 종류를 분기하지 않도록 시그니처를 일치시키는 목적이다.

### 4. 도구 description 정정 (이슈 A)

`query_business_data`의 `_DESCRIPTION`을 조회 전용에서 **"조회 및 수정/삭제"**로 명확화해, "연봉을 바꿔줘" 같은 변경 요청이 SQL 도구로 라우팅되게 한다. `manage_permission` description은 권한(멤버십·폴더 접근권·SQL 실행 권한)에 한정됨을 대비시켜 경계를 분명히 한다.

> 한계: LLM 도구 선택은 비결정적이라 단위 테스트로 완전 보장은 어렵다. description 정정으로 라우팅 정확도를 높이되, e2e mock 테스트로 의도한 도구가 호출되는 시나리오를 검증한다.

### 5. ADR-0034 작성

read-only 2차 방어선을 "이중 계정"으로 진화시킨 결정을 기록한다. ADR-0020은 폐기가 아니라 보강(`super_readers` 격리·스키마 분리는 유효, 실행 계정만 ro/rw 이원화). 방어심층 3층을 명시: **게이트(1차) + 쓰기계정 분리(2차) + WHERE 가드(3차)**.

## 방어심층 (변경 후)

```
앱(일반 계정)  ──> RAG 운영 객체                              [SQL 도구 접근 불가]
SQL 도구 SELECT ──> business 스키마 (sql_tool_ro: SELECT)
SQL 도구 UPDATE/DELETE ──> business 스키마 (sql_tool_rw: SELECT/UPDATE/DELETE)
                            ↑ 게이트 update_delete 통과분만 + WHERE 필수
```

- 1차: capability 게이트(`justify_update_delete@capability:sql`, engineering/c_level만)
- 2차: 쓰기는 별도 계정 — 게이트 우회 시에도 ro 풀로는 임의 쓰기 불가
- 3차: WHERE 없는 대량 변경은 risk 단계 DENY

## 테스트 (DoD)

- **risk 단위**: WHERE 없는 UPDATE→DENY, WHERE 없는 DELETE→DENY, WHERE 있는 UPDATE→update_delete, WHERE 있는 DELETE→update_delete
- **핸들러 단위**: SELECT→ro_pool 호출, UPDATE→rw_pool 호출(풀 선택 검증, mock)
- **e2e(mock)**: engineering UPDATE(WHERE 有)→JUSTIFY interrupt→resume(사유)→rw 실행→행수 반환 / 무소속 UPDATE→DENY / WHERE 없는 UPDATE→DENY
- 회귀: `tests/app` 전체 + `tests/scripts/test_seed_business`
- eval 회귀 점수: RAG 검색·생성 경로 무영향이라 생략(명시)

## 범위 밖 (YAGNI)

- INSERT, DDL 지원
- statement timeout / row limit 수치 조정(ADR-0020 미해결 항목 — 본 설계와 독립)
- resume 완료 시 사유가 user 메시지로 저장되는 이력 표시 불일치(별개 후속 이슈)
