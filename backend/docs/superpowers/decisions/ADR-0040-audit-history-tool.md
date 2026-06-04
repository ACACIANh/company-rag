# ADR-0040: query_audit_history 도구 — ReAct 루프 내 감사 이력 조회

> **Status**: 🟢 적용완료

**Date**: 2026-06-04
**Context**: 관리자가 채팅 인터페이스를 통해 `gate_audit_log`를 자연어로 조회할 수 있어야 한다. 별도 대시보드 없이 기존 ReAct 루프에 통합하는 것이 목표다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| query_audit_history ToolHandler (ADR-0023 패턴) | RISK_SELECT 재사용, admin 체크는 execute() 안에서 처리. 기존 패턴 일관성 유지. |
| 별도 read_node 그래프 추가 | 그래프 노드/엣지 추가 복잡도가 크고, ALLOW 경로로 충분히 처리 가능 |
| RISK_GRANT 재사용 | 권한 부여와 조회를 같은 capability에 묶는 것은 의미론적으로 부적절 |
| execute() 인터페이스에 user_id 추가 | 기존 SqlToolHandler·PermissionToolHandler 모두 수정 필요하므로 변경 범위가 과도함 |

## Decision
**선택: query_audit_history ToolHandler (ADR-0023 패턴)**

- 위험도: `RISK_SELECT` 재사용 → 게이트 자동 ALLOW, 추가 FGA 튜플 불필요
- admin 체크: `execute()` 안에서 `fga_client.user_roles()` 조회 — 인터페이스 변경 없이 처리
- caller_id 전달: `tool_gate_node`가 `{**args, "__caller_id": user_id}` 주입 → `plan()`이 `params_json`에 포함
- 멀티파라미터: `StructuredTool` + Pydantic `_Input` 스키마 — LLM이 구조화된 인자를 직접 채움

## Rationale

### 왜 query_audit_history ToolHandler인가?

1. **기존 패턴 재사용** (ADR-0023): ToolHandler 기반 agentic loop는 이미 검증된 구조다. 새로운 패턴 도입이 아니라 기존 도구 확장이므로 유지보수 비용이 낮다.

2. **위험도 분류가 명확**: 감사 이력 조회는 데이터 읽기만 하므로 `RISK_SELECT`로 충분하다. FGA에서 read capability를 이미 정의했으므로 추가 튜플 정의가 불필요하다.

3. **admin 권한 체크 캡슐화**: execute() 안에서 `fga_client.user_roles(user_id)`를 호출해 런타임에 admin 역할을 확인한다. 
   - 인터페이스(ToolHandler ABC)를 변경하지 않음
   - 비관리자 호출 시 도구 실행 후 "권한 없음" 메시지 반환 (gate 통과는 했지만 실제 데이터 조회 거부)

4. **caller_id 자동 주입**: `tool_gate_node`가 args dict에 `__caller_id` 키를 추가하므로, 어떤 관리자가 조회했는지를 audit log에 기록할 수 있다. 도구 구현에서 `params_json`에 포함되므로 추가 처리가 필요 없다.

5. **LLM 친화적 인자 전달**: StructuredTool + Pydantic _Input 스키마를 사용하면 LLM이 자연어를 보고 구조화된 필터(예: `start_date`, `end_date`, `action_type`)를 직접 채운다. JSON 문자열 파싱보다 오류율이 낮다.

### 대안 검토

- **별도 read_node**: 그래프 엣지 추가(router → read_node → end), condition 함수, state 확장 등 복잡도가 크다. ALLOW 루트만으로 충분하다.
- **RISK_GRANT 재사용**: 권한 부여(permission 변경)와 조회(read-only)는 서로 다른 capability다. 의미론적 오염을 피해야 한다.
- **execute() 인터페이스에 user_id 추가**: 모든 ToolHandler 구현체(SqlToolHandler, PermissionToolHandler 등)를 수정해야 하므로 변경 범위가 과도하다.

## Consequence

**긍정적**:
- 관리자만 조회 가능 (FGA admin role 멤버십 체크)
- 기존 agentic loop와 일관된 경험 제공
- 도구 확장이므로 프론트엔드/그래프 구조 변경 불필요
- 도구 호출 자체도 gate_audit_log에 기록됨

**부정적**:
- 비관리자가 도구 호출 시 gate는 ALLOW하지만 execute()에서 거부하므로, 사용자 경험상 "실패"로 보일 수 있음 (LLM이 "권한이 없습니다" 응답)
- 위험도가 `RISK_SELECT`로 낮으므로 추가 게이트 프로세스(예: 승인) 없이 바로 실행 → 실수로 대량 조회할 여지 있음 (audit trail로 추적 가능)

## Related

- ADR-0023: Tool Call 에이전트화
- ADR-0028: Capability-Permission 모델
- ADR-0018: 결정 감사 로그
