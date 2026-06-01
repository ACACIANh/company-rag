# 프로젝트 안내 (Claude Code용)
> CLAUDE.md에 내용 추가 시, 상세 내용은 별도 파일로 분리하고 경로 참조만 남긴다. 본문에는 hard constraint와 판단 기준만 유지한다.

## 프로젝트 개요
LangGraph 기반 RAG 챗봇. Python 3.11+, `langgraph` + `langchain-anthropic`.

## 참조 문서
- LangGraph 설계/구현 질문 → **먼저 `docs/langgraph-guide/INDEX.md`**. ADR과 어긋나는 패턴 제안 시 거부하거나 ADR 갱신 PR 먼저 제안할 것.
- ADR 목록 → `docs/superpowers/decisions/`

## 레이어 경계 (절대 위반 금지)
- `core/`는 LangGraph를 모른다. import 금지.
- `app/`는 `core/`의 인터페이스(ABC)만 의존. 구현체 직접 참조 금지.
- `app/graph/nodes/`는 순수 함수. State in → State out. side effect는 `core/` 호출로만.

## 핵심 아키텍처 결정
- State: `AgentState(TypedDict)`. `MessagesState` 및 임의 dict 금지.
- 라우터: `router_node` — `route` 필드로 doc_search/web_search/tool_call 분기 (`app/graph/nodes/router.py`)
- HITL: `interrupt()` — tool_call 경로에만, `MemorySaver` checkpointer 필수 (`app/graph/nodes/confirm.py`)
- FGA: 폴더 트리 pre-filter. `ListObjects(can_read, folder)`로 사용자가 읽을 수 있는 폴더 목록을 받아, 상위 노드만 추린 뒤 그 path prefix에 매칭되는 청크만 검색. 권한 주체는 부서(department) 단위 — 개인 단위 메타데이터·sensitivity 없음. 목표 설계: `DESIGN.md`.
- FGA 캐시: PostgreSQL TTL 캐시 (Redis 미사용).

## 작업 규칙
1. **새 노드/엣지 추가 전**: `docs/langgraph-guide/INDEX.md` 먼저 읽기.
2. **상태 스키마 변경**: `AgentState(TypedDict)` 확장만. 임의 dict 금지.
3. **외부 API 호출 노드**: retry + timeout 필수.
4. **테스트**: 노드는 순수 함수로 작성해 단위 테스트 가능하게.
5. **`core/` 추상화**: ABC·미연결 구현체 삭제 제안/실행 금지. 학습 목적 + 구현체 교체 가능성 유지.
6. **수술적 변경**: 요청에 해당하는 줄만 수정. 인접 코드·주석·포맷 수정 금지. 기존 스타일 유지. 내 변경이 만든 dead code만 정리.

## 코딩 원칙 (Karpathy 4원칙)
상세: `docs/superpowers/decisions/2026-05-26-karpathy-guidelines-audit.md`

1. **먼저 생각하라**: 구현 전 가정 명시. 불확실하면 질문.
2. **단순함 우선**: 요청한 것만 구현. 추측성 기능·추상화 금지. (`core/` 예외: 규칙 5)
3. **수술적 변경**: 요청에 해당하는 줄만. (규칙 6 참조)
4. **목표 중심**: 멀티스텝 착수 전 "단계 → 검증" 명시.

## 결정 기록 규칙
`AskUserQuestion`으로 설계·방향·도구 선택 발생 시 즉시 ADR 생성.
경로: `docs/superpowers/decisions/YYYY-MM-DD-<topic>.md` / 템플릿: `docs/superpowers/decisions/_template.md`

## DoD (Definition of Done)
1. 단위 테스트 추가
2. `tests/eval/runner.py`로 회귀 점수 확인 (하락 시 원인 명시)
3. 새 의존성·패턴 도입 시 ADR 작성 및 CLAUDE.md ADR 섹션 갱신

## Phase 작업 워크플로우
1. `git checkout -b feat/phase-N`
2. 작업 및 커밋
3. PR 생성 — description에 DoD 체크리스트 포함 (`plan/plan.md` DoD 항목 기준)
4. merge 후 태그: `git tag phase-N && git push origin phase-N`

> Phase 1~5 완료. Phase 1=e6c2124, Phase 2=954a693
