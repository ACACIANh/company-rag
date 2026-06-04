# ADR-0048: 도구 라벨 자동 발견(tool label auto-discovery)

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-05
**Context**: 응답에 어떤 도구(rag/sql/permission/audit)를 썼는지 사용자가 알 수 없었다. 표시용으로 도구명→라벨 매핑 테이블을 따로 두면 새 도구를 추가할 때마다 그 테이블과 (필요하면) 프론트 라벨 맵까지 같이 손봐야 해 동기화 부채가 쌓인다.

## Options
### 라벨 출처(SSOT)
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 도구 레지스트리를 라벨 SSOT로 — 각 도구가 `label` self-declare | 도구 정의 한 곳에서 이름·라벨이 함께 산다. 새 도구는 클래스에 `label` 한 줄. **채택** |
| B. 별도 하드코딩 매핑 테이블(`{name: label}`) | 도구 정의와 매핑이 떨어져 있어 추가 시 양쪽을 손봐야 함 — 동기화 부채 |

### 프론트 표시
| 선택지 | 트레이드오프 |
|--------|------------|
| 백엔드가 라벨 문자열을 보내고 프론트는 그대로(uppercase) 렌더 | 새 도구 추가 시 프론트 무수정. **채택** |
| 프론트에 별도 표시 라벨 맵 | 백엔드 라벨과 별개로 또 동기화해야 함 — 동일 부채 |

## Decision
**선택: A(레지스트리 SSOT) + 프론트는 라벨 그대로 렌더**

1. **self-declare**: 각 `ToolAgent`가 `label` 클래스 속성을 선언한다(rag/sql/permission/audit).
2. **자동 수집**: `app/graph/tools/registry.py::tool_label_map()` 이 `_TOOL_CLASSES`를 돌며 `{cls.name: cls.label}`를 만든다. 수동 매핑 테이블 없음.
3. **라벨 계산**: `app/graph/tool_labels.py::collect_tool_labels(route, agent_messages)`. `doc_search`는 도구가 아니라 RAG 검색 라우트이므로 `["rag"]`로 단일 매핑(SSOT의 유일한 명시적 예외). `agent` 라우트는 `tool_label_map()`으로 호출된 도구명을 라벨로 변환(중복 제거, 첫 등장 순서 유지).
4. **전파**: 응답 `Answer.tools`(core/models.py), `answer_question`/`stream_answer`(app/graph/builder.py), `ChatResponse.tools`(app/api/chat.py)로 흘려보내고, 프론트는 라벨 문자열을 대문자로 그대로 `ToolHeader`에 렌더한다 → 새 도구 추가 시 프론트 수정 불필요.
5. **파리티 가드**: 테스트로 `tool_label_map()` 키가 등록된 도구 집합과 일치함을 보장(라벨 누락·고아 매핑 방지).

## Rationale
- 라벨을 도구 정의와 같은 곳에 두면 "새 도구 = `_TOOL_CLASSES`에 한 줄 + 클래스에 `label` 한 줄"로 끝나, 분리된 매핑 테이블을 손볼 일이 없다. 동기화 지점을 하나로 줄이는 것이 핵심.
- 프론트가 백엔드 라벨을 그대로 렌더하므로 표시 어휘가 백엔드 한 곳에서 정해진다. 프론트에 별도 맵을 두면 또 다른 동기화 부채가 생긴다.
- `doc_search`만 예외인 이유: 라우트 자체가 RAG 검색이라 호출된 "도구"가 없어 레지스트리에서 라벨을 끌어올 대상이 없다 — 한 줄 명시가 가장 단순하다.

## 관련
- [ADR-0033](ADR-0033-naming-role-vs-how.md) — 외부 노출 이름은 역할(role) 기준. 라벨도 역할명(rag/sql/permission/audit)
- [ADR-0049](ADR-0049-capability-audit-summary.md) — 같은 작업의 capability 감사 요약
