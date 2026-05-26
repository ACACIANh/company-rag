# RAG 아키텍처 역할 구조

> 설계 철학: 외부 의존은 **추상(ABC) ← 구현체 ← Adapter** 3층으로 분리한다.
> (1) 추상화된 객체로 개념을 먼저 학습하고, (2) 구현체는 언제든 교체 가능하게 둔다.

```
shared/                    # 추상 역할 + 교체 가능한 구현체 (LangGraph 무관)
├── Model        ← 데이터 구조 정의
├── Config       ← 환경변수 → 설정값
│
├── 〔인덱싱 파이프라인〕
│   ├── Loader   ← 원문 적재 (예: MarkdownLoader)
│   ├── Chunker  ← 문서 → 청크 (예: FixedSizeChunker)
│   ├── Embedder ← 텍스트 → 벡터 변환
│   └── Indexer  ← Loader+Chunker+Embedder+VectorStore 조립
│
├── 〔질의 파이프라인〕
│   ├── Retriever ← 질의 → 유사 청크 탐색
│   └── Reranker  ← 검색 결과 재정렬 (기본 NoOpReranker, Retriever에 주입)
│
├── 〔외부 의존 추상〕  ABC ← 구현체 ← Adapter
│   ├── LLM         ← 텍스트 생성 (Anthropic / OpenAI)
│   │   └── Adapter ← LangChain 호환 변환 (배선 대기)
│   └── VectorStore ← 벡터 저장 & 검색 (PostgreSQL)
│       └── Adapter ← LangChain 호환 변환 (배선 대기)
│
├── 〔오케스트레이션 추상〕  Pipeline / Step / Context
│        ↑ 프레임워크 독립적 개념 모델. graphs/ 가 이를 LangGraph로 *구현* (추상↔구체 한 쌍)
│
└── 〔횡단 관심사〕  Observability
    ├── Tracer ← 노드 단위 span (rag_basic 배선 예정)
    ├── Cache  ← LLM / Embedder 결과 캐시
    └── Eval   ← Evaluator + metrics

graphs/                    # 구체 오케스트레이션 (LangGraph 구현)
└── Orchestrator           ← 위 역할들을 조합해 Q&A 실행 (rag_basic = StateGraph)
    └── Prompt             ← 각 워크플로우 자체 관리 (graphs/prompts.py)
```

## 추상 ↔ 구체 관계 메모
- `shared/orchestrator/`(Pipeline·Step·Context)는 "파이프라인이란 무엇인가"를 프레임워크 없이
  표현한 **개념 모델**이다. `graphs/rag_basic.py`(LangGraph StateGraph)는 같은 개념의 **구체 구현**이다.
- 따라서 둘은 중복이 아니라 추상↔구체 한 쌍으로 본다.
- 주의: `Context`(query/chunks/answer_text)와 `RagState`(MessagesState 확장)는 같은 상태를 두 번
  표현한다. 학습용으로 병존시키되, 새 워크플로우 추가 시 둘 중 하나로 정렬할지 그때 결정한다.

## 배선(연결) 현황
연결 안 된 추상화는 "삭제 대상"이 아니라 "첫 연결 지점이 정해지지 않은 것"이다.

| 추상화 | 상태 | 첫 연결 지점 |
|---|---|---|
| LLM / VectorStore / Embedder / Loader / Chunker | ✅ 그래프·스크립트에 연결됨 | — |
| Reranker | ✅ BasicRetriever에 주입(기본 noop) | 추후 cross-encoder 구현체로 교체 |
| LangChain Adapter (LLM/Retriever) | ⏳ 정의·테스트만 | LangChain API를 요구하는 컴포넌트 도입 시 |
| Tracer | ⏳ Pipeline에서만 사용 | rag_basic 노드 span + Answer.trace |
