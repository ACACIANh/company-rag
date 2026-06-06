# ADR-0055: 데모 경로 성능 최적화 — 독립 FGA 조회 병렬화(안전) + LLM 구조 변경 보류

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-06
**Context**: 데모 15장면(`scripts/demo_bench.py`)을 3회 반복 측정해 병목을 찾고, 동작 불변·저위험 최적화만 적용했다. 가장 큰 레버(LLM 호출 직렬화)는 중위험이라 사용자 결정(“측정 후 안전한 것만 적용”)에 따라 보류·기록한다.

## 측정 (gpt-4.1-mini, reranker=none, postgres session/cache, LangSmith on)

| 지표 | 값 |
|------|----|
| 회차 총합 median (baseline) | **86.1s** / 15장면 |
| 지배 비용 | **OpenAI LLM 왕복 ~99%** (RAG 장면당 router+rewrite+grade+generate+hallucination ≈ 5콜) |
| 장면 변동 | OpenAI 꼬리지연이 ±0.3~40s (단일 장면이 6.9s→45.3s까지 튐) |
| 권한 스냅샷 FGA 조회 (마이크로벤치, 노이즈 제거) | **88.9ms → 64.4ms (1.38×)**, 값 동일성 OK |

병목 분석은 8-에이전트 병렬 워크플로우로 수행(59 findings, 저위험·동작불변 39). 핵심: 권한 스냅샷이 부서·역할·폴더·capability(5)·테이블(3) = **~15개 독립 FGA round-trip을 완전 순차** 실행.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| **A. 독립 FGA 조회 병렬화 (asyncio.gather)** | 동작 불변(값·순서 보존), 저위험. 단 데모 wall-clock의 ~99%가 LLM이라 체감 효과는 작음(FGA 계층 1.38×, 장면당 ~25ms) |
| B. router + rewrite_query 병렬화 | 둘은 ADR-0031상 `question` 입력 공유·상태 키 분리라 병렬 가능. 마이크로벤치 실측 **순차 1341ms → 병렬 735ms = 606ms/장면(1.83×)**(절감≈min(rewrite,router), 초기 ~2s 추정은 과대). ~9s/회차(~10%) 잠재. 그래프 토폴로지 변경이라 **중위험** |
| C. grade_documents LLM 휴리스틱 대체 / FGA 클라이언트 재사용 | RAG 품질·보안 경로에 영향 가능 → 사용자 사인오프 필요 |

## Decision
**선택: A 적용, B·C 보류(기록).**

적용(동작 불변, 저위험):
1. `app/graph/tools/permission_tool.py::execute` — 권한 스냅샷 5개 독립 조회를 `asyncio.gather`로 병렬(직렬 ~15 → wall-clock ~2 round-trip).
2. `_resolve_capabilities` — 5개 위험도 `gate_decision` 병렬(표시 순서 보존).
3. `core/fga/client.py::user_accessible_tables` — 3개 테이블 viewer check 병렬(sorted 순서 보존).
4. `app/graph/nodes/tool_gate.py` — `user_roles`+`user_departments` 병렬.

검증: 단위테스트 641 통과 + 병렬성 회귀 가드 4개 추가(동시 in-flight peak 측정 — 순차로 되돌리면 실패). 마이크로벤치(`scripts/micro_bench_fga.py`)로 값 동일성·1.38× 확인.

## Rationale
- 데모 시간은 **OpenAI LLM 왕복이 지배**(~99%). 안전한 비-LLM 최적화는 정확·검증 가능하지만 end-to-end wall-clock(86.1s→84.69s)에선 초 단위 LLM 변동에 묻힌다 — 정직하게 “FGA 계층에서만 측정 가능한 1.38×”로 보고한다.
- **실질 레버는 LLM 호출 구조(B)**다. router와 rewrite_query는 `state["question"]`만 입력으로 쓰고(ADR-0031) 서로 다른 상태 키를 쓰므로 병렬화가 의미상 안전하나, LangGraph 그래프 재배선(중위험)이라 사용자가 “안전한 것만”을 택해 이번 범위에서 제외했다.
- C(grade_documents 제거·FGA 클라이언트 재사용)는 품질/보안/생명주기 리스크가 있어 별도 ADR + 사인오프 대상.

## 후속
- **B. router∥rewrite 병렬화 — 머지완료(PR #95)**. fan-out/fan-in 그래프 재배선 대신 **합성 노드**(`app/graph/nodes/route_and_rewrite.py`)로 `rewrite_query_node`·`router_node`를 `asyncio.to_thread`+`gather` 동시 실행(LLMClient.complete가 동기 블로킹이라 스레드 필요). 출력 키 분리로 단순 병합. retry 루프도 합성 노드로 동일 보존. 마이크로벤치 **606ms/장면(1.83×)** 절감. 3회 end-to-end는 OpenAI 꼬리지연으로 장면 median 합 -4%(짧은 장면서 선명).
- **C. FGA 클라이언트/커넥션 재사용 — 구현완료(브랜치 `perf/fga-client-reuse-warmup`)**. `check()`마다 `OpenFgaClient`(aiohttp 세션) 재생성하던 것을 공유 컨텍스트매니저 `_shared()`로 단일 클라이언트 재사용(lazy 생성, lifespan에서 `aclose()`). 마이크로벤치 check당 **8.2→2.3ms(3.65×)**, 권한 스냅샷(A 병렬화 포함) **64.4→8.4ms(7.7×)**, 원본 대비 ~10.6×. 재사용·aclose 회귀 가드 테스트 2개.
- **D. 콜드스타트 lifespan 워밍업 — 구현완료(브랜치 `perf/fga-client-reuse-warmup`)**. 첫 요청(scene 01)의 lazy import·첫 TLS/세션 비용을 부팅 시점에 미리 지불(FGA·임베딩·LLM 각 1콜 동시, best-effort). 실측 부팅+워밍업 6.8s, **첫 /chat 8.0s→1.13s(~7s 단축)**.
- 측정 하니스: `scripts/demo_bench.py`(15장면 반복·HITL resume·장면별 지연), `scripts/micro_bench_fga.py`(FGA 순차vs병렬, 클라이언트 재사용 반영).
