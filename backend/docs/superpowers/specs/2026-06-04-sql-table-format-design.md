# SQL 조회 결과 마크다운 표 포매팅 설계

## 개요

SQL 도구(`query_business_data`)가 반환하는 행 데이터를 최종 사용자 응답에서 마크다운 표로 보여준다. 현재는 파이프(` | `) 구분 텍스트로만 출력되어 가독성이 낮다.

## 현재 상태

`sql_tool.py:_format_rows()`가 생성하는 출력:

```
name | salary
Alice | 5000
Bob | 6000
```

에이전트 LLM이 이 `ToolMessage` content를 읽고 최종 답변을 자유롭게 생성하므로, 표 형식이 최종 응답에 보존된다는 보장이 없다.

## 목표

- SQL 조회 결과가 최종 사용자 응답에서 **마크다운 표**로 렌더링된다.
- 단일 컬럼 집계(예: `COUNT(*)`) 포함 모든 행 결과를 표로 통일한다.
- 결과 없음(`(결과 없음)`) 케이스는 변경하지 않는다.

## 설계

### 변경 1: `_format_rows()` (sql_tool.py:31-38)

proper markdown table 형식으로 수정한다.

**변경 전:**
```python
def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join(str(r[c]) for c in cols))
    return "\n".join(lines)
```

**변경 후:**
```python
def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    data_lines = ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join([header, separator, *data_lines])
```

출력 예시:
```
| name | salary |
| --- | --- |
| Alice | 5000 |
| Bob | 6000 |
```

### 변경 2: `_SYSTEM` 프롬프트 (agent.py:9-12)

LLM이 도구에서 받은 마크다운 표를 그대로 응답에 포함하도록 지시를 추가한다.

**변경 전:**
```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다."
)
```

**변경 후:**
```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다."
)
```

## 테스트 계획

- `_format_rows()` 단위 테스트: 다중 컬럼·다중 행, 단일 컬럼, 빈 결과 케이스 커버
- 기존 `test_sql_tool.py`에 표 형식 검증 케이스 추가

## 영향 범위

| 파일 | 변경 |
| --- | --- |
| `app/graph/tools/sql_tool.py` | `_format_rows()` 본문 수정 |
| `app/graph/nodes/agent.py` | `_SYSTEM` 문자열 1문장 추가 |
| `tests/unit/test_sql_tool.py` | 단위 테스트 추가 |
