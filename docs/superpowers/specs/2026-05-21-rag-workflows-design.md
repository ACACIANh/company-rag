# RAG Workflows 비교 학습 프로젝트 설계

**날짜:** 2026-05-21  
**목적:** RAG 기반 에이전트 구현 방법론을 단계별로 비교 학습 및 포트폴리오

---

## 개요

동일한 회사 내부 문서(docs/)를 대상으로 네 가지 다른 오케스트레이션 방식으로 Q&A 시스템을 구현한다. 공통 RAG 인프라(`shared/`)를 재사용하고, 각 `workflows/` 하위 디렉토리는 오케스트레이션 방식만 다르게 구현한다.

---

## 디렉토리 구조

```
company-agent/
├── docs/                          # 공유 회사 내부 문서 (참고 프로젝트에서 복사)
├── .env                           # 공유 환경 변수 (LLM API 키, Chroma 설정 등)
├── requirements.txt               # 전체 의존성
├── main.py                        # 단일 진입점
│
├── shared/                        # 공용 RAG 인프라 (모든 workflows에서 import)
│   ├── config.py                  # .env 로드 및 Config 데이터클래스
│   ├── models.py                  # Chunk, SearchResult, Answer DTOs
│   ├── llm/
│   │   ├── base.py                # ABC: complete(prompt: str) -> str
│   │   ├── factory.py             # LLM_PROVIDER env var 기반 인스턴스 생성
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   └── adapters/
│   │       └── langchain_adapter.py  # shared.LLMClient → LangChain Runnable 변환
│   ├── vector_store/
│   │   ├── base.py                # ABC: add(), search(), count()
│   │   ├── factory.py
│   │   ├── chroma_store.py
│   │   └── adapters/
│   │       └── langchain_retriever.py  # shared.VectorStore → BaseRetriever 변환
│   ├── indexer/
│   │   └── indexer.py             # docs/*.md → chunks → vector store
│   └── retriever/
│       └── retriever.py           # query → embedding → VectorStore.search()
│
├── evals/                         # 비교 평가셋
│   ├── questions.yaml             # 공통 질문 + 기대 키워드/출처
│   └── runner.py                  # --mode all 비교 실행 로직
│
└── workflows/                     # 오케스트레이션 방식 비교
    ├── 01_simple/                 # 순수 Python, 프레임워크 없음
    │   └── qa.py
    ├── 02_1_langchain_basic/      # LangChain LCEL 2-Step
    │   ├── chain/
    │   │   └── chain.py
    │   └── qa.py
    ├── 02_2_langchain_agentic/    # LangChain ReAct Agent
    │   ├── tools/
    │   │   └── rag_tool.py
    │   ├── agent/
    │   │   └── agent.py
    │   └── qa.py
    └── 03_langgraph/              # LangGraph 라우팅 챗봇
        ├── nodes/
        │   ├── router.py          # 질문 유형 분류 및 분기 결정
        │   ├── rag.py             # shared retriever 사용
        │   └── direct.py         # RAG 없이 직접 답변
        ├── graph/
        │   └── graph.py           # StateGraph 조립
        └── qa.py
```

---

## 실행 방식

```bash
# 인덱스 빌드 (최초 1회)
python main.py --build-index

# 각 워크플로우 실행
python main.py --mode simple          # 01_simple
python main.py --mode langchain       # 02_1_langchain_basic
python main.py --mode agentic         # 02_2_langchain_agentic
python main.py --mode langgraph       # 03_langgraph

# 전체 비교 실행 (동일 질문을 4가지 방식으로)
python main.py --mode all --question "연차는 며칠이야?"
```

`main.py`는 `--mode`에 따라 해당 `workflows/<dir>/qa.py`의 `run(question: str) -> Answer`를 동적으로 import해서 실행한다. `--mode all`은 `evals/runner.py`를 통해 4가지 방식의 결과를 나란히 출력한다.

---

## 공통 인터페이스

모든 `qa.py`는 동일한 함수 시그니처를 구현한다:

```python
def run(question: str) -> Answer:
    ...
```

`Answer`는 `shared/models.py`에 정의된 공유 DTO:

```python
@dataclass
class Answer:
    text: str
    sources: list[str]
    trace: list[dict] | None = None  # 워크플로우별 내부 실행 흔적
```

`trace` 필드는 워크플로우마다 다른 내용을 담는다:
- `01_simple`: `None` (단순 선형 흐름)
- `02_1_langchain_basic`: LCEL 단계별 입출력
- `02_2_langchain_agentic`: ReAct 루프의 thought/action/observation
- `03_langgraph`: 방문한 노드 시퀀스 및 router 분기 결정

---

## 각 워크플로우 설계

### 01_simple — 순수 Python
- `shared/retriever` → `shared/llm` 직접 호출
- 프레임워크 없이 RAG 파이프라인의 본질적 흐름을 드러냄
- 학습 포인트: retrieve → prompt 조립 → LLM 호출의 수동 과정

### 02_1_langchain_basic — LangChain LCEL 2-Step
- `chain.py`: `retriever | prompt | llm` LCEL 파이프라인
- `shared/vector_store/adapters/langchain_retriever.py`로 `BaseRetriever` 변환
- `shared/llm/adapters/langchain_adapter.py`로 `Runnable` 변환
- 학습 포인트: LCEL의 파이프 연산자, 어댑터가 추상화 충돌을 어떻게 해결하는지

### 02_2_langchain_agentic — LangChain ReAct Agent
- `rag_tool.py`: `shared/retriever`를 `@tool`로 래핑
- `agent.py`: `create_react_agent`로 Tool 선택 자율화, trace에 ReAct 루프 기록
- 학습 포인트: Agent가 직접 Tool을 선택하는 ReAct 루프, 01/02_1과의 제어 흐름 차이

### 03_langgraph — LangGraph 라우팅
- `router.py`: 질문 유형 분류 (RAG 필요 여부 판단)
- `rag.py`: `shared/retriever` 사용, RAG 답변 생성
- `direct.py`: RAG 없이 LLM 직접 답변
- `graph.py`: `StateGraph`로 노드/엣지 조립
- 학습 포인트: 상태 그래프 기반 제어 흐름, 노드 추가만으로 기능 확장 가능

**확장 포인트:** `nodes/email.py` 추가 + `graph.py` 엣지 연결만으로 이메일 발신 등 기능 추가 가능

```
[입력] → [router] → [rag] → [answer] → [출력]
                 ↘ [direct] ↗
                 ↘ [future: email] ↗
```

---

## 환경 변수 (.env)

```bash
LLM_PROVIDER=openai          # openai | anthropic
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

VECTOR_STORE=chroma
CHROMA_MODE=embedded         # embedded | http
CHROMA_PATH=./.chroma

EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

---

## 의존성 (requirements.txt 주요 항목)

```
# 공통
openai
anthropic
sentence-transformers
chromadb
python-dotenv

# LangChain (02_1, 02_2)
langchain
langchain-openai
langchain-community

# LangGraph (03)
langgraph
```

---

## 학습 비교 포인트 요약

| 항목 | 01_simple | 02_1_langchain | 02_2_agentic | 03_langgraph |
|------|-----------|----------------|--------------|--------------|
| 오케스트레이션 | 수동 Python | LCEL Chain | ReAct Agent | StateGraph |
| 제어 흐름 | 선형, 명시적 | 선형, 선언적 | 동적 (LLM 결정) | 그래프 기반 |
| 확장성 | 코드 수정 필요 | Chain 교체 | Tool 추가 | 노드/엣지 추가 |
| 디버깅 용이성 | 매우 쉬움 | 쉬움 | 어려움 | 중간 |
| 프레임워크 의존 | 없음 | LangChain | LangChain | LangGraph |
| LLM 호출 횟수 | 1회 | 1회 | N회 (ReAct) | 1~N회 (분기) |
| trace 내용 | None | LCEL 단계 | ReAct 루프 | 노드 시퀀스 |

---

## evals/ — 비교 평가셋

`evals/questions.yaml` 예시:

```yaml
questions:
  - question: "연차는 며칠이야?"
    expected_keywords: ["연차", "일수"]
    expected_source: "vacation-policy.md"
  - question: "코드 리뷰 가이드라인이 뭐야?"
    expected_keywords: ["PR", "리뷰"]
    expected_source: "code-review-guide.md"
```

`--mode all` 실행 시 동일 질문셋을 4가지 방식으로 돌리고 답변 텍스트, 출처, trace, 응답 시간을 나란히 출력한다.
