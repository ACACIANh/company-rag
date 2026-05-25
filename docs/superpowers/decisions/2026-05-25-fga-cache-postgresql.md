# Decision: listObjects 캐싱 전략 — Redis → PostgreSQL 변경

**Date**: 2026-05-25
**Context**: 기존 ADR(2026-05-23)에서 Redis Cloud를 우선 검토하기로 했으나, 기존 PostgreSQL 재사용으로 변경

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| Redis Cloud | 관리형, 빠르지만 신규 서비스 추가 필요 |
| PostgreSQL (기존 세션 DB) | 인프라 추가 없음, Redis보다 약간 느리지만 충분 |

## Decision

**선택: PostgreSQL — 기존 POSTGRES_DSN 재사용**

## Rationale

세션 스토어로 이미 PostgreSQL을 사용 중이므로 인프라를 추가하지 않는다.
캐시 크기가 작고(유저 수 = row 수) TTL이 60초로 짧아 성능 차이가 무시 가능하다.
`PermissionCacheBackend` ABC로 추후 Redis 교체가 가능하다.
