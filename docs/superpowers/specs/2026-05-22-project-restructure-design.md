# 프로젝트 구조 재편 설계

> 작성일: 2026-05-22  
> 목표: plan/plan.md 기준으로 현재 코드베이스를 재편하여 AI 위임 개발 구조 확립

---

## 배경

현재 구조(`shared/` + `graphs/`)는 LangGraph 학습 목적으로 구축됐다.  
이제 plan/plan.md(Agentic RAG 기획안)를 실제 개발 기준으로 채택하며,  
현재 코드를 plan.md 구조에 맞춰 이전한다.

---

## 목표 디렉토리 구조

```
app/
├── graph/
│   ├── state.py          # AgentState(TypedDict) — plan.md §3
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── retrieve.py   # retrieve_node (shared/retriever 활용)
│   │   └── generate.py   # generate_node (shared/llm 활용)
│   ├── edges.py          # 조건부 분기 로직 (Phase 2~)
│   └── builder.py        # build_graph() — 현 graphs/rag_basic.py 역할
├── ingestion/
│   ├── __init__.py
│   ├── chunker.py        # shared/chunker 구현체 직접 사용 (래퍼 아님)
│   ├── embedder.py       # shared/embedder 구현체 직접 사용
│   └── indexer.py        # shared/indexer 구현체 직접 사용
├── tools/                # Phase 3에서 채움
│   └── __init__.py
├── api/
│   ├── __init__.py
│   └── chat.py           # FastAPI /chat 엔드포인트 skeleton
└── config.py             # shared/config.py 이동

shared/                   # ABC + 구현체 + Adapter만 유지
├── llm/                  # LLMClient ABC + Anthropic/OpenAI + LangChainAdapter
├── vector_store/         # VectorStore ABC + Chroma/Qdrant + LangChainAdapter
├── embedder/             # Embedder ABC + 구현체
├── retriever/            # Retriever ABC + BasicRetriever (NoopReranker 주입)
├── reranker/             # Reranker ABC + NoopReranker
├── models.py             # 도메인 모델 (변경 없음)
└── observability/        # Tracer/Cache/Eval (변경 없음)

graphs/                   # 이전 후 삭제
tests/
├── unit/                 # 기존 tests/shared/ → tests/unit/shared/
├── integration/
└── eval/
    ├── dataset.jsonl
    └── run_eval.py       # 기존 eval_suite/runner.py 이동

plan/
└── plan.md               # AI 위임 기준 문서 (수정 없음)
```

---

## State 스키마 (plan.md §3 채택)

```python
from typing import TypedDict, Annotated, Literal
from operator import add

class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: Annotated[list[dict], add]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[str]
    hallucination_passed: bool
```

CLAUDE.md ADR: `MessagesState` 상속 → `AgentState(TypedDict)` 로 변경.

---

## architecture-review.md 코드 수정 병행

| 우선순위 | 파일 | 변경 내용 |
|---|---|---|
| P1 | `shared/llm/factory.py` | `create_chat_llm` → `LLMClient` + `LangChainLLMAdapter` 경유로 수정 |
| P2 | `shared/retriever/basic_retriever.py` | `reranker: Reranker = NoopReranker()` 기본값 주입 |

---

## 마이그레이션 전략

1. `app/` 신규 생성 (기존 코드 건드리지 않음)
2. `graphs/rag_basic.py` 로직을 `app/graph/` 로 이전
3. `shared/config.py` → `app/config.py` 이동, 전체 import 경로 업데이트 (re-export 없음)
4. `graphs/` 디렉토리 삭제
5. `eval_suite/` → `tests/eval/` 이동
6. import 경로 전면 업데이트
7. 기존 테스트 전부 통과 확인

---

## DoD

- [ ] `python -m pytest` 전체 통과
- [ ] `scripts/chat_rag_basic.py` 동작 확인
- [ ] `eval_suite/runner.py`(이전 후 경로) 회귀 점수 유지
- [ ] CLAUDE.md ADR 갱신 완료
