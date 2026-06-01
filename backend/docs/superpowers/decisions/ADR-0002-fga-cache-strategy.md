# ADR-0002: listObjects 캐싱 전략

> **Status**: 🟢 적용완료 — 저장소 구체화는 [ADR-0009](ADR-0009-fga-cache-postgresql.md)로 갱신

**Date**: 2026-05-23
**Context**: OpenFGA `listObjects` 호출 성능 한계 발생 시 캐싱 레이어 도입 방식 결정

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| 미도입 (직접 호출) | 구현 단순, 문서 수 적을 때 충분, 성능 이슈 시 재검토 필요 |
| Redis Cloud | 관리형 무료 플랜 존재, 즉시 도입 가능, 유료 전환 시 비용 발생 |
| 오픈소스 외부 캐싱 DB (Valkey/KeyDB 등) | 완전 무료, 직접 운영 필요 |

## Decision

**선택: Redis Cloud 우선 검토 → 유료 한계 시 오픈소스 대안(Valkey/KeyDB) 도입**

## Rationale

현재는 성능 이슈가 확인되지 않았으므로 선제 도입하지 않는다. 이슈 발생 시 Redis Cloud 무료 플랜으로 먼저 검증하고, 비용 문제가 생기면 Valkey(Redis 포크, Apache 2.0) 또는 KeyDB를 대안으로 조사한다. 캐시 무효화는 권한 변경 이벤트(write 후 flush)로 처리한다.
