# Phase 3: Agent화 — 라우터 + 도구 분기 설계

> 작성일: 2026-05-22
> 목표: 질문 유형에 따라 doc_search / web_search / tool_call 경로를 자율 선택하는 라우터 추가

---

## 배경

Phase 2에서 Self-RAG(rewrite → retrieve → grade → generate → halluc) 루프가 완성됐다.
Phase 3는 이 루프 앞에 **LLM 기반 라우터**를 추가해 세 가지 도구 경로로 분기한다.
사내 문서 질문은 기존 Self-RAG 경로를, 외부 정보는 웹 검색을, 작업 요청은 HITL 확인 후 도구 실행 경로를 탄다.

---

## 전체 그래프 구조

```
START → rewrite_query → router_node
                            │
              ┌─(doc_search)┤
              │             ├─(web_search)──────────────────────────────┐
              │             └─(tool_call)──→ confirm_node(interrupt()) ──┤
              │                                                          │
              ▼                                                          │
         retrieve_node                              web_search_node / tool_executor_node
              ↓                                                          │
       grade_documents_node                                              │
              ↓ (route_after_grade)                                      │
     [rewrite_retry 루프 최대 2회]                                        │
              ↓                                                          │
          generate_node ◀────────────────────────────────────────────────┘
              ↓
    check_hallucination_node
              ↓
             END
```

**경로별 특성:**
- `doc_search`: 기존 Self-RAG 루프 완전 재활용. grade → retry 포함.
- `web_search`: grade 루프 없이 바로 generate. 웹 결과는 신뢰 소스로 취급.
- `tool_call`: `interrupt()`로 사용자 확인 후 실행. grade 루프 없음. 거부 시 END.

---

## 새 노드 명세

### `router_node` — `app/graph/nodes/router.py`

**입력:** `state["rewritten_question"]`
**출력:** `{"route": "doc_search" | "web_search" | "tool_call", "tool_input": str}`

- LLM에게 ROUTER_PROMPT를 주어 세 가지 중 하나를 출력하게 함
- 파싱 실패 또는 알 수 없는 응답 → `doc_search` fallback
- `tool_input`: tool_call 경로에서 도구에 넘길 파라미터 문자열 (다른 경로는 빈 문자열)

### `web_search_node` — `app/graph/nodes/web_search.py`

**입력:** `state["rewritten_question"]`
**출력:** `{"documents": list[SearchResult]}`

- `WebSearchRetriever` ABC(= `Retriever`)를 주입받아 호출
- 결과가 없으면 빈 리스트 반환 (generate에서 "정보 없음" 처리)

### `confirm_node` — `app/graph/nodes/confirm.py`

**입력:** `state["rewritten_question"]`, `state["tool_input"]`
**출력:** `{"confirmed": bool}`

- `interrupt({"message": ..., "tool_input": state["tool_input"]})` 호출
- 재개(resume) 시 사용자 응답(True/False)을 `confirmed`에 저장
- 사용자 거부 → `confirmed=False` → `route_after_confirm`이 END로 라우팅

### `tool_executor_node` — `app/graph/nodes/tool_executor.py`

**입력:** `state["tool_input"]`
**출력:** `{"documents": list[SearchResult]}`

- Phase 3에서는 Mock 구현: `tool_input`을 파싱해 더미 SearchResult 반환
- 실제 API 연동은 Phase 4 이후

---

## 공유 레이어 — WebSearchRetriever

```
shared/retriever/
├── base.py                          # Retriever ABC (변경 없음)
└── adapters/
    ├── tavily_retriever.py          # TavilyRetriever(Retriever)
    └── duckduckgo_retriever.py      # DuckDuckGoRetriever(Retriever)
```

- 둘 다 `Retriever.retrieve(query, top_k) -> list[SearchResult]` 구현
- `web_search_node`는 어떤 구현체가 주입되든 무관 (ABC만 의존)
- `TavilyRetriever`: `TAVILY_API_KEY` 환경변수 필요
- `DuckDuckGoRetriever`: API 키 불필요, `duckduckgo-search` 패키지 사용

---

## State 변경

`app/graph/state.py`에 필드 2개 추가:

```python
class AgentState(TypedDict):
    # ... 기존 필드 유지 ...
    confirmed: bool     # confirm_node 결과 (tool_call 경로용, 기본값 False)
    tool_input: str     # router가 파싱한 도구 파라미터
```

---

## 엣지 (조건부 분기)

`app/graph/edges.py`에 함수 2개 추가:

```python
def route_after_router(state) -> str:
    return state["route"]  # "doc_search" | "web_search" | "tool_call"

def route_after_confirm(state) -> str:
    return "tool_executor" if state["confirmed"] else "end"
```

**전체 조건부 엣지 목록:**
| 출발 노드 | 엣지 함수 | 목적지 |
|---|---|---|
| `router_node` | `route_after_router` | `retrieve` / `web_search` / `confirm` |
| `confirm_node` | `route_after_confirm` | `tool_executor` / END |
| `grade_documents` | `route_after_grade` (기존) | `generate` / `increment_retry` |
| `check_hallucination` | `route_after_hallucination` (기존) | END / `generate` |

---

## builder.py 변경

- `checkpointer=InMemorySaver()` 추가 (interrupt() 동작 필수)
- 신규 노드 등록 및 엣지 연결

---

## 테스트 전략

### 노드 단위 테스트

| 파일 | 핵심 케이스 |
|---|---|
| `test_router.py` | LLM → route 설정; 알 수 없는 응답 → doc_search fallback; tool_call → tool_input 파싱 |
| `test_web_search.py` | mock Retriever → documents 반환; 빈 결과 처리 |
| `test_confirm.py` | interrupt() 호출 확인; confirmed=True/False 설정 |
| `test_tool_executor.py` | Mock 도구 → SearchResult 포맷 반환 |
| `test_tavily_retriever.py` | API mock → SearchResult 변환 |
| `test_duckduckgo_retriever.py` | 패키지 mock → SearchResult 변환 |

### 통합 테스트 (test_builder.py 추가)

- doc_search 질문 → retrieve 경로 진입
- web_search 질문 → web_search_node 호출
- tool_call 질문 → interrupt() 발생
- tool_call + 사용자 거부 → END 조기 종료
- tool_call + 사용자 승인 → tool_executor → generate → END

### 평가셋 확장

`tests/eval/questions.yaml`에 라우팅 평가용 질문 추가:
- `doc_search` 유형 10개 (기존 활용)
- `web_search` 유형 10개
- `tool_call` 유형 10개

**DoD 기준:** 올바른 도구 선택률 90% 이상

---

## DoD

- [ ] 노드 단위 테스트 전부 PASS
- [ ] `pytest tests/ -q --ignore=tests/eval` 전부 PASS (회귀 없음)
- [ ] 라우팅 정확도 평가셋 90% 이상
- [ ] tool_call 경로에서 interrupt() 동작 확인
- [ ] CLAUDE.md ADR 갱신 (router 노드, HITL 방식 추가)
