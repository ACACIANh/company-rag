# ADR-0004: 구문서 소유자 미지정 시 일괄 처리 방침

> **Status**: 🟣 대체됨 → [ADR-0011](ADR-0011-folder-tree-access-model.md) — 권한 모델이 폴더 트리 기반으로 전환되어 owner/team/sensitivity 개념이 제거됨. 본 정책은 더 이상 유효하지 않다.

**Date**: 2026-05-23
**Context**: 마이그레이션 대상 구문서 중 소유자 정보가 없는 경우 OpenFGA owner 튜플을 누구에게 부여할지 결정

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| sensitivity=internal + 수동 정제 | 안전하지만 정제 전까지 owner 미지정 상태 유지 |
| 별도 컬렉션 격리 | RAG 대상에서 제외되어 검색 누락 발생 가능 |
| 팀장 → CEO → super admin 순 자동 지정 | 즉시 접근 가능, 책임 소재 명확 |

## Decision

**선택: 팀장 우선 → 팀장 없으면 CEO → CEO도 없으면 super admin**

## Rationale

소유자 공백 상태로 두면 접근 권한 체계가 불완전해진다. 조직 계층 순서로 fallback owner를 지정하면 즉시 RAG에 포함 가능하고, 이후 실제 담당자가 확인하면 owner를 재지정(tuple 교체)하면 된다. super admin은 시스템 관리자 계정으로 최후 보루 역할을 한다.

### 구현 로직

```python
def resolve_owner(doc, org_graph) -> str:
    if doc.team_id:
        lead = org_graph.get_team_lead(doc.team_id)
        if lead:
            return lead
    ceo = org_graph.get_ceo()
    if ceo:
        return ceo
    return "super_admin"
```
