# 프로젝트 안내 (Claude Code용)

## 프로젝트 개요
LangGraph 기반 RAG 챗봇. 단일 ReAct 에이전트로 시작해 멀티에이전트(Supervisor 패턴)로 확장 예정.

- **언어/런타임**: Python 3.11+
- **핵심 의존성**: `langgraph`, `langchain`, `langchain-anthropic` (또는 openai), 벡터 DB는 추후 결정
- **개발 단계**: 초기 (스캐폴딩 ~ 첫 RAG 워크플로우)

## 참조 문서
LangGraph 관련 설계/구현 질문이 생기면 **먼저 `docs/langgraph-guide/INDEX.md`를 읽고**,
필요한 섹션 파일로 들어가세요. 원본 책: https://wikidocs.net/book/16723

각 섹션 파일에는:
- 핵심 개념 요약
- 우리 프로젝트에서 이 개념을 어떻게 쓰는지 (또는 안 쓰는지)
- 원본 위키독스 URL (더 깊이 필요하면 web_fetch)

## 아키텍처 결정 (ADR)

| 영역 | 결정 | 참조 |
|---|---|---|
| 상태 관리 | `AgentState(TypedDict)` — plan.md §3 기준 (MessagesState 미사용) | `app/graph/state.py` |
| 메모리 | 개발: `InMemorySaver`, 다음 단계: `SqliteSaver` | `docs/langgraph-guide/02-memory.md` |
| 에이전트 시작점 | `create_agent` (Part 2-2) | `docs/langgraph-guide/03-agent.md` |
| RAG | `app/graph/` 워크플로우 슬라이스 (Phase 단위 확장) → `plan/plan.md` 기준 | `docs/langgraph-guide/04-rag.md` |
| State | `AgentState(TypedDict)` — plan.md §3 기준, MessagesState 미사용 | `app/graph/state.py` |
| 워크플로우 구조 | Phase 하나 = `app/graph/` 슬라이스. 신규 Phase는 nodes/ + edges.py 확장 | `plan/plan.md` |
| 멀티에이전트 | Supervisor 패턴 (Part 4-2-1) | `docs/langgraph-guide/05-multi-agent.md` |
| 스트리밍 | `messages` 모드 (토큰 스트리밍) | `docs/langgraph-guide/06-streaming.md` |
| HITL/가드레일 | 결정론적 가드레일 우선, 민감 도구는 `interrupt()` | `docs/langgraph-guide/07-safety.md` |
| 라우터 | LLM 기반 `router_node` — `route` 필드로 doc_search/web_search/tool_call 세 경로 분기 | `app/graph/nodes/router.py` |
| HITL | `interrupt()` — tool_call 경로에만 적용, `MemorySaver` checkpointer 필수 | `app/graph/nodes/confirm.py` |
| 웹 검색 | `Retriever` ABC + Tavily/DuckDuckGo 어댑터 — 주입 방식으로 교체 가능 | `shared/retriever/adapters/` |

## 결정 기록 규칙 (Decision Log)

`AskUserQuestion` 툴로 선택이 발생할 때마다 **즉시** ADR 파일을 생성한다.

- **경로**: `docs/superpowers/decisions/YYYY-MM-DD-<topic>.md`
- **형식**:
  ```markdown
  # Decision: <주제>
  **Date**: YYYY-MM-DD
  **Context**: <무엇을 결정했는지 한 줄>

  ## Options
  | 선택지 | 트레이드오프 |
  |--------|------------|
  | A      | ...        |
  | B      | ...        |

  ## Decision
  **선택: <선택한 항목>**

  ## Rationale
  <왜 이 선택을 했는지 — 질문 옵션 설명 + 사용자 컨텍스트 기반>
  ```
- 커밋은 작업 완료 시점에 다른 변경사항과 함께 묶어도 되지만, 파일 생성은 선택 직후 즉시.
- 단순 프롬프트 튜닝(모델명, 포맷 등 자명한 선택)은 제외. 설계·방향·도구 선택은 반드시 기록.

## 작업 규칙
1. **새 노드/엣지 추가 전**: 관련 섹션 파일을 먼저 읽고, 책의 패턴과 어긋나면 이유를 커밋 메시지에 남길 것
2. **상태 스키마 변경**: `AgentState(TypedDict)` 확장 패턴 유지. 임의 dict 사용 금지
3. **외부 API 호출 노드**: 반드시 retry + timeout 설정. 비결정성은 노드 단위로 격리
4. **테스트**: 노드는 순수 함수로 작성해 단위 테스트 가능하게. 그래프 통합 테스트는 별도

## 디렉터리 구조
```
app/
├── graph/          # LangGraph 워크플로우 (Phase 단위 슬라이스)
│   ├── state.py    # AgentState TypedDict
│   ├── nodes/      # 노드 순수 함수
│   ├── edges.py    # 조건부 분기 (Phase 2~)
│   ├── builder.py  # 그래프 조립 + eval adapter
│   └── prompts.py  # 프롬프트 템플릿
├── ingestion/      # 문서 인덱싱 (chunker, embedder, indexer)
├── tools/          # 에이전트 도구 (Phase 3~)
└── api/            # FastAPI 엔드포인트
shared/             # ABC + 구현체 + Adapter (LangGraph 무관)
docs/
├── company/          # 회사 내부 문서 (RAG Q&A 대상)
├── langgraph-guide/  # LangGraph 레퍼런스
└── superpowers/      # 설계 문서 및 구현 계획
    ├── decisions/    # ADR — AskUserQuestion 선택 기록 (자동 생성)
    ├── plans/        # 구현 계획
    └── specs/        # 설계 스펙
plan/               # AI 위임 기준 기획서 (plan.md)
tests/
├── shared/         # shared/ 단위 테스트
├── app/            # app/ 단위 테스트
└── eval/           # 평가셋 + 회귀 테스트 (questions.yaml, runner.py)
```

## 레이어 경계 (절대 위반 금지)
- shared/ 는 LangGraph를 모른다. import 금지.
- app/ 는 shared/ 의 인터페이스(ABC)만 의존. 구현체 직접 참조 금지.
- app/graph/nodes/ 는 순수 함수. State in → State out. side effect는 shared/ 호출로만.

## LangGraph 패턴 출처
LangGraph 설계 질문은 항상 docs/langgraph-guide/INDEX.md 먼저.
ADR과 어긋나는 패턴 제안 시 거부하거나 ADR 갱신 PR을 먼저 제안할 것.

## DoD (Definition of Done)
모든 작업은 다음 충족 시 완료:
1. 단위 테스트 추가 (노드는 순수 함수 → 쉽게 작성 가능)
2. tests/eval/runner.py 로 회귀 점수 확인 (점수 하락 시 원인 명시)
3. ADR에 없는 새 의존성/패턴 도입 시 CLAUDE.md ADR 섹션 갱신

## Phase 작업 워크플로우
Phase 단위 작업은 반드시 아래 순서를 따른다:

1. **브랜치 생성**: `git checkout -b feat/phase-N`
2. **작업 및 커밋**: Phase 내 모든 커밋은 이 브랜치에서
3. **PR 생성**: DoD 체크리스트를 PR description에 포함
   ```
   ## DoD
   - [ ] (plan.md의 해당 Phase DoD 항목들)
   - [ ] 회귀 테스트 (이전 Phase recall@5 이상 유지)
   ```
4. **merge 후 태그**: `git tag phase-N && git push origin phase-N`

> Phase 1, 2는 이미 완료 (`phase-1` = e6c2124, `phase-2` = 954a693)