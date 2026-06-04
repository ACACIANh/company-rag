# Decision: 수동 테스트용 시드 데이터 전면 재구성

> **Status**: 🟢 적용완료 — TechCorp 7부서/12명/46문서 재구성 (spec: `specs/2026-06-02-techcorp-seed-rebuild-design.md`)

**Date**: 2026-06-01
**Context**: 실사용 환경처럼 체감하며 테스트하기 위해 부서·사원·문서를 대폭 늘린다. 기존 코어(13문서/4명/3부서) 위에 "추가 레이어"로 쌓을지, 전면 재구성할지 결정.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| 추가 레이어 (코어 동결 + 위에 쌓기) | eval 게이트·baseline 그대로 유지, 개발속도 타격 0. 단 기존 코어의 빈약한 구성이 토대로 남음 |
| 전면 재구성 | 현실적 단일 세계관·단단한 baseline 확보. 단 `eval/questions.yaml`(~20문항)·회귀 baseline·일부 테스트 fixture를 1회 전면 재작성 |
| 테스트코드만 (시드 불변) | 비용 최소. 단 권한 경계·prune·multi_query·리랭킹 등 "실사용 규모에서만 드러나는" 결함과 미예상 케이스를 발견 못 함 — 목적과 어긋남 |

## Decision
**선택: 전면 재구성** (문서 내용 충실도 = 기존 13개 수준의 실내용)

대상 규모(가칭 "TechCorp"): 부서 7개 + 전사(`all`), 사원 12명(복수 부서·교차 권한·권한 0 사용자 포함), 문서 ~45개.
영향 자산: `config/users.yaml`, `config/folders.yaml`, `docs/company/**`, `tests/eval/questions.yaml`, 회귀 baseline, 일부 테스트 fixture(`test_permission_node`, `conftest` 등 alice/engineering 가정 단정문).

## Rationale
- **개발속도 검토 결론**: 데이터 자체는 data-driven으로 코드와 분리돼 있어 양 증가가 개발속도를 늦추지 않는다. 사원/부서/폴더/문서 "추가"는 yaml·md 편집 + `seed_fga`·`build_index` 재실행만으로 끝나고 코드 변경 0. FGA 모델은 type 수준이라 인스턴스가 100배여도 `model.fga`·`seed_fga` 한 곳만 고치면 재생성된다. **개발속도를 늦추는 유일한 실질 경로는 `eval/questions.yaml`·baseline·fixture가 특정 코퍼스에 결합돼 있다는 점**이며, 이 비용은 "추가"가 아니라 "기존 코어 수정/교체"에서만 발생한다.
- **그럼에도 전면 재구성 선택**: "흔들리는 구조에서 쌓기보다 단단한 반석을 하나 찍어놓고 간다." eval baseline을 현실적 코퍼스 위에서 1회 재정립하면 이후 모든 회귀 측정이 실사용에 가까운 토대 위에서 이뤄져 장기적으로 이득. 재작성 비용은 1회성으로 감수한다.
- **테스트코드만으로 불충분**: 테스트코드는 예상한 케이스만 검증한다. 권한 경계(권한 0 사용자, 교차 부서), `prune_to_top_folders`, multi_query·RRF·리랭킹의 효과는 실사용 규모 데이터에서만 체감·검증된다. 따라서 풍부한 시드 데이터(실사용 결함 발견)와 테스트코드(회귀 안전망)는 대체재가 아니라 보완재로 둘 다 둔다.

## Status
**적용완료 (2026-06-02)** — ADR-0015(FGA 4축 모델) 확정으로 보류 해제. 조직 구체안·구현을 `specs/2026-06-02-techcorp-seed-rebuild-design.md` + `plans/2026-06-02-techcorp-seed-rebuild.md`로 확정·실행.

## 구현 결과 (2026-06-02)

**규모**: 부서 7개(engineering·product·design·sales·hr·finance·legal) + 전사공통 common. 사원 12명(c_level 1·무소속 1·교차부서 3·단일 7). 문서 46개(기존 15 재사용 + 신규 31). private 서브트리 4개(engineering/ops·hr·finance·legal) — ops는 public 부모 밑 서브트리 private로 ADR-0015 상속차단 경계를 자극.

**조직 구체안**: 기존 매핑(alice=engineering, bob=hr, carol=무소속, admin=c_level) 보존으로 API 인증 fixture churn 0. 신규 8명·5부서·31문서는 additive.

**검증**:
- 단위테스트 324 통과(기존 318 + 권한 매트릭스 6: 교차부서·무소속·super_reader 관통 — `tests/app/test_rag_with_fga.py`).
- 재시드(FGA 33 튜플) → 재인덱싱(89 청크 / 46 distinct source) 로컬 인프라에서 실행 완료.
- eval baseline(신 코퍼스, `user-admin` 전사 열람권 기준): **recall@1=0.700 · recall@3=0.733 · recall@5=0.733 · mrr=0.717 · kw=0.767 (errors=0/30)**.
  - aggregate에는 tool_call 6문항(expected_source 없음 → 구조상 recall 0)이 포함됨. doc_search 24문항만 보면 recall@1≈0.875 · recall@5≈0.917.
  - 실질 검색 미스 2건: `기기 분실`→security-policy(미검색), `배포 절차`→deployment-guide(동음이의 "배포"가 product/release-process 등에 분산돼 top-5 밖). **ADR-0014가 노린 "실사용 규모에서만 드러나는 검색 함정"이 그대로 관측됨** — 향후 리랭킹·multi_query 개선의 회귀 측정 토대.

**부수 발견 — eval 하니스 복구**: 신 코퍼스 eval 측정 중, eval 스크립트가 그래프 진화에 뒤처져 깨져 있던 것을 발견(데이터 재구성과 무관한 선재 버그). `eval_rag_basic.py`·`compare_reranker.py`가 (1) OpenAI 임베딩 모델을 SentenceTransformer로 하드코딩, (2) `build_graph`가 요구하는 `fga_client` 미주입. eval 측정을 위해 `get_embedder()` 팩토리 일치 + fga_client 배선(`user-admin` 전사 열람) + 인용 source basename 채점 보정을 적용(`fix(eval)` 커밋들). 지표 계층(`recall_at_k`가 `list[SourceRef]`를 받는 타입 불일치, source 폴더상대 vs basename)은 eval 스크립트 경계에서만 보정하고 프로덕션 `core/observability/eval/`는 미변경이라 했으나, 이후 `core/observability/eval/metrics.py`가 `recall_at_k(retrieved_sources: list[str], ...)` 시그니처로 수정됨 — 근본 타입 불일치 해결완료.
