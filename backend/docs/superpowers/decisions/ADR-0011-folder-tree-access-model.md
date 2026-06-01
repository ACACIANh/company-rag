# ADR-0011: 접근 권한 모델 — 문서/팀/민감도 → 폴더 트리 pre-filter 전환

> **Status: Superseded by [ADR-0015](ADR-0015-fga-public-private-super-reader.md)** — 단일 `viewer` 축 모델을 public/private/dept/super_reader 4축 모델로 확장. pre-filter 메커니즘(ListObjects(can_read)→path prefix)은 그대로 유지.

**Date**: 2026-06-01
**Context**: 기존 권한 모델(document/team + sensitivity 등급 + 개인 grant 기반 2-tier pre-filter)을 폴더 트리 상속 기반으로 전면 교체. 목표 설계는 `DESIGN.md` 참조.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| 기존 2-tier 유지 (team_id+sensitivity + personal_docs) | 이미 구현됨. 그러나 sensitivity 자동 분류가 부정확하고, 폴더 단위 조직 권한과 매핑이 안 되며 개인 grant 관리 비용이 큼 |
| 폴더 트리 + ListObjects pre-filter | 조직의 실제 폴더 구조와 1:1, 트리 상속으로 권한 정의 단순, 개인 메타·민감도 분류 불필요. OpenFGA `can_read from parent` 재귀 활용 |

## Decision

**선택: 폴더 트리 상속 모델 + `ListObjects(can_read, folder)` pre-filter**

OpenFGA 모델:

```
type user
type department
  relations
    define member: [user]
type folder
  relations
    define parent: [folder]
    define viewer: [department#member]
    define can_read: viewer or can_read from parent
```

검색 흐름 (`DESIGN.md` 기준):

1. `ListObjects(user, can_read, folder)`로 읽을 수 있는 폴더 목록 조회
2. 목록에서 상위 노드만 추림 (부모가 포함되면 자식 path는 버림)
3. vectorstore에서 추린 path prefix에 매칭되는 청크만 pre-filter 후 벡터 검색
4. 통과한 청크만 LLM에 전달해 답변 생성

## Rationale

- **권한 주체를 부서(department) 단위로 단일화** → 개인 단위 메타데이터(`personal_docs`, `user_doc_grants`)와 secret 등급 처리를 제거해 관리 비용을 낮춘다.
- **폴더 트리 상속**(`can_read from parent`)으로 상위 폴더 권한이 하위에 자동 전파되어, 문서마다 tuple을 부여하던 방식보다 정의가 단순하다.
- **sensitivity 자동 분류 제거**: 키워드 기반 `detect_sensitivity`는 오분류 위험이 컸다. 권한은 폴더 배치로만 결정한다.
- **pre-filter 메커니즘 자체는 유지**: `where_clause`를 벡터 검색 SQL에 주입하는 기존 구조를 재사용하고, 필터 축만 team/sensitivity → path prefix로 교체한다.
- CLAUDE.md의 "2-tier pre-filter, listObjects 전체 목록 미사용" 결정을 본 ADR이 대체한다. 이제 `ListObjects`로 폴더 목록을 받는 것이 정식 방식이다.

## 영향받는 결정

- **[2026-05-23-legacy-doc-owner-policy.md](2026-05-23-legacy-doc-owner-policy.md)** — superseded. sensitivity/owner 전제가 사라지므로 폐기.
- `plan/access-control.md`의 document/team/sensitivity 스키마는 본 ADR로 대체됨 (문서는 이력용으로 유지).
