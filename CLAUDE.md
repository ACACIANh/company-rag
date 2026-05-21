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
| 상태 관리 | `MessagesState` 상속해서 확장 | `docs/langgraph-guide/01-stategraph.md` |
| 메모리 | 개발: `InMemorySaver`, 다음 단계: `SqliteSaver` | `docs/langgraph-guide/02-memory.md` |
| 에이전트 시작점 | `create_agent` (Part 2-2) | `docs/langgraph-guide/03-agent.md` |
| RAG | 기본 워크플로우 → 추후 고급 RAG | `docs/langgraph-guide/04-rag.md` |
| 멀티에이전트 | Supervisor 패턴 (Part 4-2-1) | `docs/langgraph-guide/05-multi-agent.md` |
| 스트리밍 | `messages` 모드 (토큰 스트리밍) | `docs/langgraph-guide/06-streaming.md` |
| HITL/가드레일 | 결정론적 가드레일 우선, 민감 도구는 `interrupt()` | `docs/langgraph-guide/07-safety.md` |

## 작업 규칙
1. **새 노드/엣지 추가 전**: 관련 섹션 파일을 먼저 읽고, 책의 패턴과 어긋나면 이유를 커밋 메시지에 남길 것
2. **상태 스키마 변경**: `MessagesState` 확장 패턴 유지. 임의 dict 사용 금지
3. **외부 API 호출 노드**: 반드시 retry + timeout 설정. 비결정성은 노드 단위로 격리
4. **테스트**: 노드는 순수 함수로 작성해 단위 테스트 가능하게. 그래프 통합 테스트는 별도

## 디렉터리 구조 (예정)
```
src/
├── agents/         # 에이전트 정의 (create_agent 또는 StateGraph)
├── nodes/          # 재사용 가능한 노드 함수들
├── state/          # State 스키마 정의
├── tools/          # 에이전트가 쓰는 도구들
├── rag/            # 문서 로딩, 청킹, 검색
└── graphs/         # 최상위 그래프 조립
docs/
└── langgraph-guide/  # LangGraph 레퍼런스 (이 파일에서 가리키는 곳)
tests/
```

## 레이어 경계 (절대 위반 금지)
- shared/ 는 LangGraph를 모른다. import 금지.
- graphs/ 는 shared/ 의 인터페이스만 의존. 구현체 직접 참조 금지.
- nodes/ 는 순수 함수. State in → State out. side effect는 shared/ 호출로만.

## LangGraph 패턴 출처
LangGraph 설계 질문은 항상 docs/langgraph-guide/INDEX.md 먼저.
ADR과 어긋나는 패턴 제안 시 거부하거나 ADR 갱신 PR을 먼저 제안할 것.

## DoD (Definition of Done)
모든 작업은 다음 충족 시 완료:
1. 단위 테스트 추가 (노드는 순수 함수 → 쉽게 작성 가능)
2. eval_suite/runner.py 로 회귀 점수 확인 (점수 하락 시 원인 명시)
3. ADR에 없는 새 의존성/패턴 도입 시 CLAUDE.md ADR 섹션 갱신