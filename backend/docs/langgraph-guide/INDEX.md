# LangGraph 가이드 INDEX

원본 책: [LangGraph 가이드북 - 에이전트 RAG with 랭그래프](https://wikidocs.net/book/16723)

이 디렉터리는 위 책을 우리 프로젝트 관점에서 압축·재구성한 레퍼런스입니다.
각 파일에는 **핵심 요약 + 우리 프로젝트에서의 사용 방침 + 원본 URL**이 들어있습니다.
더 깊이 필요하면 원본 URL을 `web_fetch`로 가져와 읽으세요.

## 언제 어느 파일을 봐야 하나

| 상황 | 봐야 할 파일 |
|---|---|
| 새 노드/엣지/State 추가 | `01-stategraph.md` |
| 대화 히스토리/체크포인터 관련 작업 | `02-memory.md` |
| 도구 호출 에이전트 만들기/수정 | `03-agent.md` |
| 문서 로딩, 청킹, 임베딩, 검색 | `04-rag.md` |
| 에이전트 여러 개 조합, 라우팅 | `05-multi-agent.md` |
| 토큰 스트리밍, 중간 상태 노출 | `06-streaming.md` |
| PII 마스킹, 프롬프트 인젝션, 승인 워크플로우 | `07-safety.md` |

## 책 전체 구조 (원본 매핑)

### Part 1. LangGraph 기초
- 1-1 소개, 1-2 환경 설정 (생략 가능, 설치는 README 참조)
- **1-3 StateGraph** → `01-stategraph.md` (State, Node, Edge, Compile)
- **1-4 메모리** → `02-memory.md` (InMemorySaver, SqliteSaver, Time Travel)
- 1-5 서브그래프 → 필요해지면 그때 추가
- **1-6 스트리밍** → `06-streaming.md`
- 1-7 Functional API → **사용 안 함** (Graph API로 통일)

### Part 2. ReAct 에이전트
- 2-1 ReAct 개요 (개념만 알면 됨)
- **2-2 create_agent** → `03-agent.md`의 빠른 시작 섹션
- **2-3 StateGraph 커스텀 에이전트** → `03-agent.md`의 커스텀 섹션
- 2-4 Human-in-the-Loop → `07-safety.md`에 통합
- **2-5 Guardrails & Safety** → `07-safety.md`

### Part 3. RAG
- **3-1 ~ 3-4** → `04-rag.md`로 압축

### Part 4. 멀티 에이전트
- **4-1 아키텍처 패턴 + 4-2 Supervisor/Handoff** → `05-multi-agent.md`

## 학습 우선순위 (사람이 읽을 경우)
1. `01-stategraph.md` (필수)
2. `03-agent.md` → `create_agent`로 동작 확인
3. `02-memory.md` → 대화 히스토리 붙이기
4. `04-rag.md` → 검색 노드 추가
5. `06-streaming.md` → UX 개선
6. `05-multi-agent.md` → 확장 시
7. `07-safety.md` → 운영 전 필수