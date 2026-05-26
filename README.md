# company-rag

LangGraph 기반 RAG 챗봇 학습 프로젝트.

회사 내부 문서(`docs/`)를 대상으로 RAG Q&A를 구현하며, 단일 ReAct 에이전트로 시작해 멀티에이전트(Supervisor 패턴)로 확장하는 것을 목표로 합니다.

> **현재 단계**: 초기 — 공용 인프라(`shared/`)만 구현되어 있고, 워크플로우 레이어는 LangGraph 기반으로 새로 작성 중입니다.

---

## 프로젝트 구조

```
company-rag/
├── docs/                     # 회사 내부 문서 (Q&A 대상) + 가이드
│   ├── langgraph-guide/      # LangGraph 학습 노트 (INDEX.md 진입점)
│   └── *.md                  # 정책, 가이드 등
├── shared/                   # 공용 RAG 인프라 (워크플로우 무관)
│   ├── loader/               # MarkdownLoader
│   ├── chunker/              # FixedSizeChunker
│   ├── embedder/             # SentenceTransformerEmbedder
│   ├── vector_store/         # PostgreSQL (ABC + Factory)
│   ├── retriever/            # EmbeddingService + Retriever
│   ├── reranker/             # Reranker
│   ├── llm/                  # LLMClient ABC + OpenAI/Anthropic + LangChain 어댑터
│   ├── indexer/              # 문서 → 청크 → 벡터 저장소
│   ├── orchestrator/         # 공통 오케스트레이션 유틸
│   ├── observability/        # cache, tracer, eval
│   ├── models.py             # Chunk, SearchResult, Answer DTOs
│   └── config.py             # 환경변수 로드
├── scripts/
│   └── build_index.py        # 문서 인덱싱 진입점
├── eval_suite/               # 평가 데이터셋 + 러너
│   ├── questions.yaml
│   └── runner.py             # run(question) 함수를 외부 주입 받아 채점
├── tests/                    # 단위 테스트 (shared/ 대상, 85개)
└── CLAUDE.md                 # 작업 규칙 및 아키텍처 결정 (ADR)
```

---

## 빠른 시작

```bash
# 1. 가상환경 + 의존성
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip3 install -r requirements.txt

# 2. 환경변수
cp .env.example .env
# .env에 OPENAI_API_KEY (또는 ANTHROPIC_API_KEY) 입력

# 3. 문서 인덱싱 (최초 1회)
python3 -m scripts.build_index
```

### `.env` 최소 설정 (ChromaDB 기본)

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

---

## 아키텍처

### `shared/` — 워크플로우 무관 공용 인프라

ABC + Factory 패턴으로 LLM 프로바이더(OpenAI/Anthropic)와 벡터 저장소(PostgreSQL)를 추상화합니다. 모든 워크플로우는 `shared/`를 재사용합니다.

LangChain 통합을 위한 얇은 어댑터도 포함합니다:
- `shared/llm/adapters/langchain_adapter.py` — `LLMClient` → `BaseLLM`
- `shared/vector_store/adapters/langchain_retriever.py` — `VectorStore` → `BaseRetriever`

### 공통 응답 모델

```python
@dataclass
class Answer:
    text: str
    sources: list[str]
    trace: list[dict] | None = None
```

### 아키텍처 결정 (요약)

| 영역 | 결정 |
|---|---|
| 상태 관리 | `MessagesState` 확장 |
| 메모리 | 개발: `InMemorySaver` → 다음: `SqliteSaver` |
| 에이전트 시작점 | `create_agent` |
| 멀티에이전트 | Supervisor 패턴 |
| 스트리밍 | `messages` 모드 (토큰) |
| HITL/가드레일 | 결정론적 가드레일 우선, 민감 도구는 `interrupt()` |

상세 근거는 `CLAUDE.md`와 `docs/langgraph-guide/`를 참고하세요.

---

## 테스트

```bash
pytest tests/ -v          # 전체 (85개)
pytest tests/shared/      # shared 단위 테스트
```

---

## 평가

`eval_suite/runner.py`의 `run_eval(run, yaml_path)`에 워크플로우의 `run(question) -> Answer` 함수를 주입하면 `questions.yaml`을 대상으로 recall@k / keyword_hit_rate 등을 채점합니다.

```python
from eval_suite.runner import run_eval
from <your_workflow> import run

run_eval(run)
```

---

## 기술 스택

- **LLM**: OpenAI GPT / Anthropic Claude
- **임베딩**: sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`)
- **벡터 저장소**: PostgreSQL (pgvector)
- **오케스트레이션**: LangGraph (+ LangChain 어댑터)
- **테스트**: pytest, pytest-mock

---

## 참조

- `CLAUDE.md` — 작업 규칙, 아키텍처 결정
- `docs/langgraph-guide/INDEX.md` — LangGraph 학습 노트 진입점
- 원본 위키독스: https://wikidocs.net/book/16723
