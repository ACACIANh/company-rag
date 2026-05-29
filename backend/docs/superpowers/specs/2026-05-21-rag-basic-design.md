# 기본 RAG 그래프 (rag_basic) 디자인

날짜: 2026-05-21
상태: Approved (브레인스토밍 완료)
범위: 첫 LangGraph RAG 워크플로우 — `retrieve → generate` 2노드 선형 그래프

## 1. 목표

- `graphs/` 디렉터리를 새로 만들고 가장 단순한 RAG 워크플로우를 LangGraph로 구현
- 기존 `shared/retriever`, `shared/llm`, `shared/models`를 재사용 (재구현 금지)
- 단일 외부 진입점: `build_graph(retriever, llm) -> CompiledStateGraph`
- 단일 파일이지만 내부 구조는 향후 `state/`, `nodes/`로 추출하기 쉽게 구획화

## 2. 비범위 (이번 PR에서 안 함)

- 메모리 / 체크포인터 (`InMemorySaver` 등)
- 멀티에이전트, Supervisor 패턴
- 토큰 스트리밍
- 리랭킹 (다음 PR)
- retry / timeout — CLAUDE.md 규칙 위반 사실을 커밋 메시지에 명시하고 다음 PR에서 보강
- `docs/langgraph-guide/04-rag.md` 작성 (별도 PR)

## 3. 아키텍처

2노드 선형 그래프. LangGraph 의존성은 `graphs/` 경계 안에만 존재한다 (ADR: shared/는 LangGraph를 모른다).

```
START → retrieve → generate → END
```

레이어:
- `graphs/rag_basic.py`: 유일하게 LangGraph를 import 하는 파일
- `shared/retriever`, `shared/llm`, `shared/models`: 기존 인터페이스만 사용. 변경 없음

## 4. State 스키마

```python
class RagState(MessagesState):
    retrieved_docs: list[SearchResult]
```

- `MessagesState` 상속 (ADR 준수)
- `messages[-1]`이 사용자 질문 (HumanMessage)
- retrieve 노드가 `retrieved_docs`를 채움
- generate 노드가 `retrieved_docs`를 읽고 AIMessage를 append

## 5. 파일 내부 구조 (단일 파일, 추출 친화)

`graphs/rag_basic.py` 안을 4개 섹션으로 명확히 구획화한다. 각 섹션은 그대로 잘라내 별도 모듈로 옮길 수 있어야 한다.

```python
# ===== State (→ 추후 state/rag_state.py) =====
class RagState(MessagesState):
    retrieved_docs: list[SearchResult]


# ===== Nodes (→ 추후 nodes/retrieve.py, nodes/generate.py) =====
def retrieve_node(state: RagState, *, retriever: Retriever) -> dict:
    query = state["messages"][-1].content
    results = retriever.retrieve(query, top_k=5)
    return {"retrieved_docs": results}


def generate_node(state: RagState, *, llm: LLMClient) -> dict:
    question = state["messages"][-1].content
    context = "\n\n".join(d.chunk.text for d in state["retrieved_docs"])
    prompt = f"context:\n{context}\n\nquestion: {question}\nanswer in Korean."
    text = llm.complete(prompt)
    return {"messages": [AIMessage(content=text)]}


# ===== Graph assembly =====
def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(RagState)
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


# ===== Eval adapter (→ 추후 graphs/adapters.py 또는 eval_suite로) =====
def answer_question(graph, question: str) -> Answer:
    final = graph.invoke({"messages": [HumanMessage(content=question)]})
    sources = [d.chunk.source for d in final["retrieved_docs"]]
    return Answer(text=final["messages"][-1].content, sources=sources)
```

### 추출 친화 원칙

1. **노드 함수는 자유 변수/클로저 캡처 금지** — retriever/llm은 반드시 키워드 인자로 명시
2. **partial 바인딩은 `build_graph()` 안에서만** 발생 (노드 함수 자체는 의존성 객체를 모름)
3. **노드 시그니처 통일**: `(state, *, dep) -> dict` — 이동 시 graph 코드만 임포트 경로 변경
4. State는 LangGraph `MessagesState`만 의존, 도메인 타입은 `shared.models`에서 import — 이동 시 import 충돌 없음
5. `answer_question`은 graph 인스턴스를 인자로 받는 순수 함수 → 위치 자유

## 6. 외부 API

- `build_graph(retriever, llm) -> CompiledStateGraph` — 외부 진입점
- `answer_question(graph, question) -> Answer` — eval 어댑터

호출 예 (eval_suite 또는 scripts에서):
```python
from shared.config import load_config
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from graphs.rag_basic import build_graph, answer_question

config = load_config()
llm = create_llm(config)
retriever = BasicRetriever(store=..., embedder=...)
graph = build_graph(retriever, llm)

answer = answer_question(graph, "연차는 며칠이야?")
```

## 7. 에러 처리

- **첫 PR은 명시적 fail-fast**. retrieve/generate 내부의 예외는 그대로 전파
- evaluator는 이미 try/except로 감싸 `error` 필드에 기록한다 (`shared/observability/eval/evaluator.py:34`)
- 노드 내부에는 try/except 금지 — 비결정성을 노드 단위로 격리 (CLAUDE.md 작업 규칙 #3)
- CLAUDE.md의 "외부 API 호출 노드는 retry + timeout 필수" 규칙은 이번 PR에서 위반. 커밋 메시지에 명시하고 다음 PR에서 보강한다.

## 8. 테스트 계획

`tests/test_graphs/test_rag_basic.py`:

1. **`test_retrieve_node_calls_retriever_with_last_message`**
   - fake `Retriever` 주입, 고정 `SearchResult` 리스트 반환
   - 결과 state의 `retrieved_docs`가 fake가 반환한 값과 동일한지

2. **`test_generate_node_appends_aimessage_with_context`**
   - fake `LLMClient`로 받은 prompt 캡처
   - prompt 안에 retrieved_docs의 chunk.text가 포함되는지
   - 반환 dict가 `messages: [AIMessage(...)]` 구조인지

3. **`test_build_graph_end_to_end_with_fakes`**
   - fake retriever + fake llm 주입
   - `graph.invoke({"messages": [HumanMessage("q")]})` 호출
   - final state에 retrieved_docs와 AIMessage 모두 존재하는지

4. **`test_answer_question_returns_answer_dto`**
   - graph + answer_question → `Answer` DTO 검증 (text, sources)

shared 컴포넌트(retriever/llm) 단위 테스트는 이미 `tests/shared/` 에 있으므로 중복 작성하지 않는다.

## 9. eval_suite 회귀 측정

- `eval_suite/runner.run_eval(run)` 에 `run = lambda q: answer_question(graph, q)` 형태로 연결
- 별도 진입 스크립트 (`scripts/eval_rag_basic.py` 또는 ad-hoc) 로 실행 후 baseline 점수를 PR 본문에 첨부
- `mean_recall_at_k`, `mean_keyword_hit_rate`, `n_errors` 보고
- 첫 그래프이므로 baseline 자체가 기준선이 된다 — "회귀"가 아니라 "초기 측정"

## 10. CLAUDE.md ADR 갱신

ADR 테이블의 RAG 행을 다음과 같이 수정:

```
| RAG | 기본 워크플로우 (graphs/rag_basic.py) → 추후 고급 RAG | docs/langgraph-guide/04-rag.md |
```

새 의존성은 없음 (`langgraph>=0.2.0`은 이미 requirements.txt에 존재).

## 11. DoD 매핑

| spec DoD | 구현 위치 |
|---|---|
| 단위 테스트 추가 | tests/test_graphs/test_rag_basic.py |
| eval_suite/runner.py 로 회귀 점수 확인 | scripts 또는 수동 실행, PR 본문에 첨부 |
| CLAUDE.md ADR 테이블 갱신 | §10 |

## 12. 위험 / 트레이드오프

- **retry/timeout 부재**: 외부 LLM/embedding 호출 실패 시 즉시 전파. evaluator가 case 단위로 격리해 부분 진행 가능. 다음 PR에서 보강.
- **단일 파일 응집**: 노드를 같은 파일에 두면 다른 그래프(예: rag_advanced)에서 재사용이 어려움. §5의 추출 친화 원칙으로 미래 이동 비용을 최소화함.
- **프롬프트 단순함**: context+question 단순 결합. 시스템 프롬프트, 인용 형식 강제, 거절 처리는 없음. baseline 점수가 낮으면 다음 PR에서 프롬프트 개선 또는 리랭킹으로 대응.
