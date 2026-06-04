# ADR-0041: ToolHandler → ToolAgent 개명 + PermissionAgent query 액션

> **Status**: 🟢 적용완료

**Date**: 2026-06-04

## Context

`app/graph/tools/`의 에이전트 클래스들이 `plan() → gate → execute()` ReAct 루프를
직접 구현함에도 `*ToolHandler` 접미사를 사용해 ADR-0033 캡슐화 기반 명명 표준과
불일치했다. 또한 `PermissionAgent`(구 `PermissionToolHandler`)는 grant/revoke만 지원해
사용자가 챗봇을 통해 자신의 권한을 확인할 수 없었다.

## Decision

1. **전면 개명**: `ToolHandler` Protocol → `ToolAgent`, `SqlToolHandler` → `SqlAgent`,
   `AuditHistoryToolHandler` → `AuditAgent`, `PermissionToolHandler` → `PermissionAgent`.
   `registry.py` 주석 `# name -> ToolHandler` → `# name -> ToolAgent`도 반영.

2. **PermissionAgent query 액션 추가**:
   - `plan()` (sync): `action=="query"` 파싱 시 `f"query {caller} {target}", RISK_SELECT` 반환.
     관리자 확인은 async인 `execute()`로 위임 — AuditAgent 동일 패턴.
   - `execute()` (async): caller != target이면 `capability:admin` 체크. 비관리자 → 거부 메시지.
     통과 시 FGA 3종(`user_departments`, `user_roles`, `get_readable_folders`) 조회 후
     `_format_permission_snapshot()`으로 포맷.
   - `PERMISSION_PARSE_PROMPT`에 `query` 액션·`target_user_id` 파싱 지시 추가.
   - `_DESCRIPTION`에 조회 기능 예시 추가.

## Consequences

- 외부 도구명(`manage_permission`)·FGA 스키마·DB 스키마 불변.
- 기존 grant/revoke 동작 불변.
- 일반 사용자: 본인 권한(부서·역할·폴더) 조회 가능.
- 관리자(`capability:admin`): 타인 권한 조회 가능.
- 테스트: 482/482 통과.

## 관련 ADR

- [ADR-0023](ADR-0023-tool-call-agentic-loop.md) — ReAct 루프 및 ToolAgent 패턴 정의
- [ADR-0029](ADR-0029-permission-management-tool.md) — PermissionAgent 원형
- [ADR-0033](ADR-0033-terminology-naming-deadcode-cleanup.md) — 캡슐화 기반 명명 표준
- [ADR-0040](ADR-0040-audit-history-tool.md) — AuditAgent plan/execute 패턴 (query 분기 참조)
