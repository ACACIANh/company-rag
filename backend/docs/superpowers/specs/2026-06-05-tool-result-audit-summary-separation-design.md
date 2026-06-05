# 도구 결과 / 감사요약 분리 — `ToolResult` 값 객체 설계

> 작성일: 2026-06-05
> 상태: 승인됨(브레인스토밍) → 구현 대기

## 배경 / 문제

관리자가 "최근 감사이력 N건 보여줘"를 호출하면 `query_audit_history`(AuditAgent)가
마크다운 표를 반환한다. 그 표의 **결과요약(`result_summary`) 컬럼**이 사람이 읽기 어렵게 깨진다.

근본 원인 두 가지:

1. **자기참조 노이즈**: 감사조회 도구의 실행 결과(마크다운 표 전체)가 다시
   `result_summary`로 저장된다. `tool_gate.py`가 `result = handler.execute(...)` 결과를
   `str(result)[:200]`로 잘라 감사로그에 기록하기 때문. 다음 조회 때
   `_clean_result`가 그 표 조각의 `|`를 보고 "헤더:값" 변환을 시도해
   `시각: 2026-06-05 09:48, 유저: user-admin ...` 같은 의미 없는 문자열을 만든다.
2. **사후 정규식 파싱**: 완성된 마크다운 표 문자열을 읽기 단계에서 `_clean_result`가
   정규식으로 되파싱한다. SELECT 결과 행도 `emp_id / name / ... / user-admin`처럼
   컬럼 헤더만 잘려 깨진다.

즉 "원시 도구 출력을 통째로 `result_summary`에 적재하고, 읽을 때 추측 파싱"하는
구조 자체가 문제다.

## 목표 / 범위

- **모든 도구**가 "감사용 짧은 요약"을 **데이터를 쥔 시점에 직접 생성**해 저장한다.
- 읽기 단계의 정규식 추측(`_clean_result`)을 **제거**한다.
- 스키마(`gate_audit_log` 11컬럼)는 변경하지 않는다 — 저장되는 **값의 품질**만 고친다.

### 범위 밖 (후속 과제)

- 웹 전용 구조화 테이블 위젯 렌더링. 이번엔 저장 + 텍스트 표현까지만.
- **레거시 행 백필 불가**: 이미 DB에 들어간 깨진 `result_summary`는 원본이 없어
  되살릴 수 없다. 이 수정은 **앞으로 쌓이는 행에만** 적용된다. 과거 행은
  이스케이프 + 80자 컷으로 표를 깨뜨리지 않는 선까지만 보정된다.

## 설계

### 1. 값 객체 `ToolResult`

`app/graph/tools/base.py`(핸들러들과 같은 app 레이어)에 추가한다.

```python
@dataclass(frozen=True)
class ToolResult:
    text: str       # ToolMessage content — 사용자 노출 전체 텍스트(마크다운 표 등)
    summary: str    # 감사로그 result_summary — 짧은 한 줄
```

`ToolAgent` Protocol의 `execute` 반환 타입을 `str` → `ToolResult`로 변경한다.

```python
async def execute(self, planned_action: str, risk: str) -> ToolResult: ...
```

- `text`(사용자 노출)와 `summary`(감사 기록) 책임이 타입으로 분리된다.
- `frozen=True` 불변 값 객체.

### 2. 핸들러별 요약 규칙

각 핸들러가 데이터를 쥔 시점에 `summary`를 만든다.

| 도구 | 경로 | `text` | `summary` |
|---|---|---|---|
| SqlAgent | SELECT 성공 | 마크다운 표 | `"{N}행 조회"` |
| | UPDATE/DELETE 성공 | `"{N}개 행이 변경되었습니다."` | `"{N}행 변경"` |
| | 오류 | `"SQL 실행 오류: {type}"` | 동일(이미 짧음) |
| AuditAgent | 조회 성공 | 감사 마크다운 표 | `"감사이력 {N}건 조회"` |
| | 권한 없음 | `"권한 없음: ..."` | `"권한 없음"` |
| | 오류 | `"감사 이력 조회 오류: ..."` | 동일 |
| PermissionAgent | query | 권한 스냅샷 마크다운 | `"권한 스냅샷 조회({uid})"` |
| | grant/revoke | `"완료: {planned_action}"` | `"완료: {planned_action}"` |
| | 오류 | 오류 메시지 | 동일 |

`"감사이력 {N}건 조회"`가 자기참조 노이즈를 제거한다.

### 3. 노드 배선

`tool_gate.py`(88-91줄)와 `justify_execute.py`(29-33줄):

```python
result = await handler.execute(planned_action, risk)
new_messages.append(ToolMessage(content=result.text, tool_call_id=tc["id"]))
result_summary = result.summary          # str(result)[:200] 제거
```

핸들러가 짧은 `summary`를 생성하므로 노드에서의 `[:200]` 절단은 제거한다
(`gate_audit_log.result_summary`는 TEXT, 하드 제한 없음).

### 4. 읽기 단계 정리

`audit_history_tool.py`:

- `_clean_result`(65-76줄) **삭제**.
- `_format_rows`(120-121줄)는 `result_summary`를 그대로 쓰되 `|`→`\|` 이스케이프 +
  80자 컷만 적용:

  ```python
  result_col = str(r["result_summary"] or "").replace("\n", " ").replace("|", "\\|")[:80]
  ```

  레거시 깨진 행도 이스케이프 덕에 마크다운 표를 깨뜨리지 않는다(잘린 원문만 보임).
- `_merge_system_pairs`·`_SYSTEM_REASON_RE`는 JUSTIFY 쌍 dedup용이라 **유지**.
  (`re` import는 `_SYSTEM_REASON_RE`가 계속 쓰므로 유지)

### 5. 에러 처리

`execute`의 모든 분기(성공/권한없음/예외)가 `ToolResult`를 반환한다.
예외는 기존처럼 내부에서 catch한 뒤 `ToolResult(text=오류문, summary=오류문)`으로 감싼다.

## 테스트 (DoD)

1. 핸들러 3종(`SqlAgent`/`AuditAgent`/`PermissionAgent`) `execute`의 `.text`/`.summary`
   단위 테스트 추가 — SELECT/쓰기/조회/권한없음/오류 경로 각각.
2. 노드 테스트(`tool_gate`/`justify_execute`)의 **페이크 핸들러가 `ToolResult`를
   반환하도록 갱신**.
3. `tests/eval/runner.py` 회귀 점수 확인(하락 시 원인 명시).

## ADR

Protocol 계약(`execute` 반환 타입) 변경이므로 신규 ADR 작성:
`도구 결과/감사요약 분리 — ToolResult 값 객체`. CLAUDE.md ADR 섹션 갱신 +
`python -m scripts.gen_adr_index` 실행.

## 영향 범위 요약

- `app/graph/tools/base.py` — `ToolResult` 추가, `execute` 시그니처
- `app/graph/tools/sql_tool.py` — `SqlAgent.execute`
- `app/graph/tools/audit_history_tool.py` — `AuditAgent.execute`, `_clean_result` 삭제, `_format_rows`
- `app/graph/tools/permission_tool.py` — `PermissionAgent.execute`
- `app/graph/nodes/tool_gate.py` — 배선
- `app/graph/nodes/justify_execute.py` — 배선
- 테스트 + ADR + CLAUDE.md
