# company-rag

RAG(Retrieval-Augmented Generation) 기반 Q&A를 4가지 오케스트레이션 방식으로 구현하고 비교하는 학습 프로젝트입니다.

동일한 회사 내부 문서(`docs/`)를 대상으로, 공통 RAG 인프라(`shared/`)를 재사용하면서 오케스트레이션 방식만 다르게 구현했습니다.

---

## 비교 대상

| 워크플로우 | 방식 | 제어 흐름 | LLM 호출 | trace |
|---|---|---|---|---|
| `01_simple` | 순수 Python | 선형, 명시적 | 1회 | None |
| `02_1_langchain_basic` | LangChain LCEL | 선형, 선언적 | 1회 | LCEL 단계 |
| `02_2_langchain_agentic` | LangChain ReAct Agent | 동적 (LLM 결정) | N회 | thought/action/observation |
| `03_langgraph` | LangGraph StateGraph | 그래프 기반 라우팅 | 1~N회 | 노드 시퀀스 |

---

## 프로젝트 구조

```
company-rag/
├── docs/                          # 회사 내부 문서 (Q&A 대상)
├── shared/                        # 공용 RAG 인프라
│   ├── models.py                  # Chunk, SearchResult, Answer DTOs
│   ├── config.py                  # 환경변수 로드
│   ├── llm/                       # LLMClient ABC + OpenAI/Anthropic + LangChain 어댑터
│   ├── vector_store/              # VectorStore ABC + ChromaDB + LangChain 어댑터
│   ├── retriever/                 # EmbeddingService + Retriever
│   └── indexer/                   # 문서 → 청크 → 벡터 저장소
├── workflows/
│   ├── 01_simple/                 # 순수 Python RAG
│   ├── 02_1_langchain_basic/      # LangChain LCEL 2-Step
│   ├── 02_2_langchain_agentic/    # LangChain ReAct Agent
│   └── 03_langgraph/              # LangGraph 라우팅 챗봇
├── eval_suite/                    # 평가 데이터셋 + 실행 진입점 (questions.yaml + runner.py)
├── tests/                         # 단위 테스트 (25개)
└── main.py                        # 단일 CLI 진입점
```

---

## 빠른 시작

```bash
# 1. 저장소 클론 후 이동
git clone https://github.com/ACACIANh/company-rag.git
cd company-rag

# 2. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. 의존성 설치
pip3 install -r requirements.txt

# 4. 환경변수 설정
cp .env.example .env
# .env를 열어 OPENAI_API_KEY (또는 ANTHROPIC_API_KEY) 입력

# 5. 문서 인덱싱 (최초 1회)
python3 main.py --build-index

# 6. 실행
python3 main.py --mode simple -q "연차는 며칠이야?"
```

---

## 설치 및 실행

### 1. 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

```bash
cp .env.example .env
# .env에 API 키 입력
```

**.env 최소 설정 (ChromaDB 기본):**
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

**.env Qdrant Cloud 사용 시 추가:**
```
VECTOR_STORE=qdrant
QDRANT_URL=https://xxx.qdrant.io:6333
QDRANT_API_KEY=your-api-key
QDRANT_COLLECTION=documents
```

### 2. 문서 인덱싱 (최초 1회)

```bash
python3 main.py --build-index
```

### 3. 각 워크플로우 실행

```bash
python3 main.py --mode simple     -q "연차는 며칠이야?"
python3 main.py --mode langchain  -q "코드 리뷰 가이드가 뭐야?"
python3 main.py --mode agentic    -q "온보딩 절차가 어떻게 돼?"
python3 main.py --mode langgraph  -q "보안 정책에서 비밀번호 규정이 뭐야?"
```

### 4. 4가지 방식 동시 비교

```bash
python3 main.py --mode all -q "연차는 며칠이야?"
```

출력 예시:
```
======================================================================
질문: 연차는 며칠이야?
======================================================================

[SIMPLE]  (1.23s)
  답변: 연차는 15일입니다.
  출처: vacation-policy.md

[LANGCHAIN]  (1.45s)
  답변: 연차는 15일입니다.
  출처: vacation-policy.md
  trace (1단계):
    {'step': 'retriever', 'docs_count': 3, 'sources': ['vacation-policy.md']}
...
```

---

## 아키텍처

### shared/ — 공용 인프라

모든 워크플로우가 동일한 `shared/` 인프라를 사용합니다. ABC + Factory 패턴으로 LLM 프로바이더(OpenAI/Anthropic)와 벡터 저장소(ChromaDB)를 추상화합니다.

LangChain 워크플로우(`02_1`, `02_2`)를 위한 얇은 어댑터 레이어도 포함합니다:
- `shared/llm/adapters/langchain_adapter.py` — `LLMClient` → `BaseLLM`
- `shared/vector_store/adapters/langchain_retriever.py` — `VectorStore` → `BaseRetriever`

### 공통 인터페이스

모든 `qa.py`는 동일한 시그니처를 구현합니다:

```python
def run(question: str) -> Answer: ...
```

```python
@dataclass
class Answer:
    text: str
    sources: list[str]
    trace: list[dict] | None = None
```

### LangGraph 확장성

`03_langgraph`는 노드/엣지 추가만으로 기능을 확장할 수 있습니다:

```
[입력] → [router] → [rag] → [출력]
                 ↘ [direct] ↗
                 ↘ [future: email 발신] ↗
```

---

## 테스트

```bash
pytest tests/ -v        # 전체 (25개)
pytest tests/shared/    # shared 단위 테스트 (20개)
pytest tests/workflows/ # 워크플로우 테스트 (5개)
```

---

## 기술 스택

- **LLM**: OpenAI GPT / Anthropic Claude
- **임베딩**: sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`)
- **벡터 저장소**: ChromaDB / Qdrant Cloud
- **오케스트레이션**: LangChain LCEL, LangGraph
- **테스트**: pytest, pytest-mock
