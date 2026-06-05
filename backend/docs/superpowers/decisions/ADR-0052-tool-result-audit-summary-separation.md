# ADR-0052: 도구 결과/감사요약 분리 — ToolResult 값 객체

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: `ToolAgent.execute`가 `str`을 반환하고, 노드가 그 문자열을 다시 잘라(`[:200]`) 감사요약으로 쓰는 구조에서 감사이력 도구 자신의 마크다운 표가 `result_summary`에 적재돼 가독성이 붕괴됐다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| A. `execute` → `str` 유지 + 별도 `audit_summary()` 메서드 | 완성된 문자열을 재파싱해야 해 안티패턴 잔존. 핸들러마다 이중 구현 부담. **기각** |
| B. `execute` → `ToolResult(text, summary)` 값 객체 반환 | 데이터 보유 시점에 요약 생성. 노드는 `.text`/`.summary`만 참조. **채택** |

## Decision

**선택: B — `ToolResult(text, summary)` 값 객체**

### 구현 세부

**`app/graph/tools/base.py`** — `ToolResult` dataclass 신설:
```python
@dataclass
class ToolResult:
    text: str       # 사용자 노출 (마크다운 표 / 메시지)
    summary: str    # 감사로그(result_summary)용 짧은 한 줄
```

**각 핸들러가 데이터를 쥔 시점에 요약 생성:**

| 핸들러 | summary 형식 |
|--------|------------|
| SqlAgent (SELECT) | `"N행 조회"` |
| SqlAgent (UPDATE/DELETE) | `"N행 변경"` |
| AuditAgent | `"감사이력 N건 조회"` |
| PermissionAgent (query) | `"권한 스냅샷 조회(uid)"` |
| PermissionAgent (write) | `"완료: ..."` |

**노드 변경:**
- `tool_gate_node`: `result.text` → ToolMessage, `result.summary` → 감사로그 `result_summary`
- `justify_execute`: 동형 적용

**읽기 단계 `_clean_result` 정규식 제거**: 감사이력 조회 시 마크다운 표 파편을 되파싱하던 정규식을 삭제. 표시 단계는 `result_summary`의 파이프 이스케이프(`|` → `\|`) + 80자 컷만 적용.

## Rationale

- **자기참조 노이즈**: `query_audit_history` 결과가 마크다운 표(수십 행)인데, 이를 `:200` 슬라이스한 문자열이 `result_summary`에 저장되면 감사이력 조회 결과가 다시 감사이력에 등장하는 자기참조 루프가 발생한다. 핸들러가 데이터 보유 시점에 "N건 조회" 한 줄을 만들면 이 구조 자체가 불가능해진다.
- **재파싱 안티패턴 제거**: `_clean_result` 정규식은 완성된 마크다운 표를 되파싱해 SELECT 결과까지 깨뜨렸다. 원천 데이터에서 요약을 만들면 파싱이 불필요하다.
- **스키마 무변경**: `gate_audit_log.result_summary` 컬럼 타입·제약 변경 없이 적재 값만 바뀐다.

## 대안 기각 이유

- **`audit_summary()` 별도 메서드 (Option A)**: `execute`가 반환한 완성 문자열에서 다시 N건을 추출하려면 정규식 또는 상태 공유가 필요하다. `_clean_result`와 동일한 안티패턴이 형태만 바뀌어 잔존한다. 각 핸들러에 `execute`/`audit_summary` 두 메서드를 강제해 인터페이스가 비대해진다.

## 영향

- **스키마**: `gate_audit_log` 무변경.
- **레거시 행**: 백필 불가(forward-only). 과거에 적재된 깨진 `result_summary`는 이스케이프+컷으로 표를 추가로 깨뜨리지 않는 선까지만 보정된다.
- **`_merge_system_pairs`**: JUSTIFY 쌍 dedup 로직은 변경 없이 유지.
- **웹 전용 테이블 위젯 렌더링**: `result_summary`를 전용 위젯으로 렌더링하는 작업은 범위 밖(후속 과제).

## 관련

- [ADR-0023](ADR-0023-tool-call-agentic-loop.md) — 도구 에이전트 추상화(`ToolAgent` 기반)
- [ADR-0040](ADR-0040-audit-history-tool.md) — 감사이력 조회 도구(`query_audit_history`) — 자기참조 문제의 발원 도구
- [ADR-0048](ADR-0048-tool-label-auto-discovery.md) — 도구 라벨 자동 발견
- [ADR-0049](ADR-0049-capability-audit-summary.md) — capability 안내 감사 요약
