# 아키텍처 리뷰: `architecture-roles.md` vs 실제 구현

> 작성일 2026-05-22 · 대상 커밋 `2ef25f3` · 근거: 실제 소스 코드(`shared/`, `graphs/`, `eval_suite/`)
>
> **전제(설계 철학)**: 이 프로젝트는 추상화를 의도적으로 선호한다.
> (1) 추상화된 객체로 **개념을 먼저 학습**하는 것이 목표이고, (2) **구현체는 언제든 교체될 수 있다**고 본다.
> 따라서 "아직 안 쓰니 삭제"가 아니라 "**언제·어디에 연결할지**"로 평가한다.

## TL;DR

`architecture-roles.md`의 역할 분리(Model/Config/LLM/VectorStore/Embedder/Retriever/Indexer + Adapter)는
방향이 옳고, 실제 코드도 그 의존성 흐름과 레이어 경계(`shared/`에 LangGraph import 0건)를 **잘 지킨다**.
ABC + 구현체 + factory 패턴은 "교체 가능성"이라는 목표에 정확히 부합한다.

남는 과제는 **삭제가 아니라 정합성 맞추기** 두 가지다.

1. **문서가 실제보다 작다** — 실제로 존재하는 핵심 추상화(Loader, Chunker, Reranker, Observability=Tracer/Cache/Eval, 그리고 orchestrator의 Pipeline/Step/Context)가 다이어그램에 없다. 학습용 지도라면 **이 추상화들이야말로 다이어그램에 있어야 한다.**
2. **추상화 일부가 아직 워크플로우에 배선되지 않았다** — 삭제 대상이 아니라 **"연결 로드맵"의 대상**이다. 단, 추상화를 *깨뜨리는* 한 곳(`create_chat_llm`)은 철학과 어긋나므로 손봐야 한다.

→ 결론: 다이어그램을 실제 추상화 전부를 담도록 **확장**하고, 각 추상화에 "첫 연결 지점"을 명시해 *추상 → 구현 → 배선*의 학습 경로를 완성한다.

---

## 1. 실제 구조 (트리)

```
shared/                          # 공용 인프라 — LangGraph 무관 (경계 준수 ✓)
├── models.py                    # Document, Chunk, SearchResult, Answer
├── config.py                    # Config + load_config()
├── llm/
│   ├── base.py                  # ABC LLMClient                     ← 교체축
│   ├── anthropic_client.py / openai_client.py   ← 교체 가능한 구현체 2종 ✓
│   ├── factory.py               # create_llm() ✓ / create_chat_llm() ⚠️추상화 누수
│   └── adapters/langchain_adapter.py   # LangChainLLMAdapter (배선 대기)
├── vector_store/
│   ├── base.py / postgres_store.py / factory.py  ← 구현체 1종 ✓
│   └── adapters/langchain_retriever.py # LangChainRetrieverAdapter (배선 대기)
├── embedder/                    # ABC + sentence_transformer + adapters/
├── loader/                      # ★문서 누락 (ABC + markdown_loader)
├── chunker/                     # ★문서 누락 (ABC + fixed_size_chunker)
├── reranker/                    # ★문서 누락 (ABC + noop) — 배선 대기
├── retriever/basic_retriever.py
├── indexer/indexer.py
├── orchestrator/                # ★문서 누락 — 추상 오케스트레이션 (Pipeline/Step/Context)
└── observability/               # ★문서 누락
    ├── tracer.py                # 배선 대기
    ├── cache.py
    └── eval/                    # Evaluator, metrics

graphs/
└── rag_basic.py                 # 구체 오케스트레이터 (LangGraph StateGraph)

eval_suite/runner.py             # questions.yaml 회귀 평가
scripts/                         # build_index, chat_rag_basic, eval_rag_basic
tests/                           # 19개 테스트 — 추상화별 단위 테스트 잘 갖춤 ✓
```

---

## 2. 문서 vs 실제 대조표

| `architecture-roles.md` 역할 | 실제 구현 | 상태 |
|---|---|---|
| Model | `shared/models.py` | ✅ 일치 |
| Config | `shared/config.py` | ✅ 일치 |
| LLM + Adapter | `shared/llm/` (ABC+구현체 2종+adapter) | ✅ 추상화 모범 사례 |
| VectorStore + Adapter | `shared/vector_store/` (ABC+구현체 2종+adapter) | ✅ 추상화 모범 사례 |
| Embedder | `shared/embedder/` | ✅ 일치 |
| Retriever | `shared/retriever/basic_retriever.py` | ✅ 일치 |
| Indexer | `shared/indexer/indexer.py` | ✅ 일치 |
| workflows/Orchestrator | `graphs/rag_basic.py` (LangGraph) | ⚠️ 위치·이름 불일치 (`workflows/` 디렉터리 없음) |
| Orchestrator/Prompt | `generate_node` 인라인 f-string (`rag_basic.py:40`) | ⚠️ "워크플로우 자체 관리"는 맞으나 추출 권장 |
| — | `shared/loader/`, `shared/chunker/` | ❌ 문서 누락 (Indexer 필수 의존) |
| — | `shared/reranker/` | ❌ 문서 누락 (배선 대기) |
| — | `shared/observability/` (Tracer/Cache/Eval) | ❌ 문서 누락 (횡단 관심사) |
| — | `shared/orchestrator/` (Pipeline/Step/Context) | ❌ 문서 누락 — **추상 오케스트레이션 개념** |

---

## 3. 관찰 (추상화 관점으로 재평가)

### ✅ 잘 된 점 — 추상화 목표에 부합
- 모든 외부 의존(LLM/VectorStore/Embedder/Loader/Chunker)이 **ABC + 구현체 + factory**로 분리돼 있어
  "구현체 교체 가능성"이라는 목표를 정확히 만족한다. LLM·VectorStore는 이미 구현체가 2종씩이라 교체축이 실증된다.
- `shared/`에 LangGraph import가 **0건** — 추상 인프라와 구체 오케스트레이션의 경계가 깨끗하다.
- 추상화마다 단위 테스트가 붙어 있어(`tests/shared/*`) 개념 학습·계약 검증 용도로도 적합하다.

### 🟢 관찰 1. `shared/orchestrator/`는 "추상 오케스트레이션", `graphs/`는 "구체 오케스트레이션"
- `Pipeline`(`pipeline.py:6`)/`Step`(`step.py:6`)/`Context`(`context.py:7`)는 오케스트레이션을
  프레임워크 독립적으로 표현한 **개념 모델**이다. LangGraph 없이 "파이프라인이란 무엇인가"를 학습하기 좋다.
- `graphs/rag_basic.py`는 같은 개념을 LangGraph로 구현한 **구체 버전**이다(`rag_basic.py:48-55`).
- 즉 둘은 "중복"이 아니라 **추상 ↔ 구체 한 쌍**으로 볼 수 있다. → 삭제하지 말고, 둘의 관계를 문서에 명시하자.
  - **단 결정 필요**: `Context`(query/chunks/answer_text)와 `RagState`(MessagesState 확장, `rag_basic.py:24`)는 같은 상태를 두 번 표현한다. 학습용으로 병존시킬지, 아니면 `graphs`가 `shared.orchestrator`의 개념을 *구현*하는 형태로 정렬할지 한 줄로 합의해두면 혼선이 준다.

### 🟢 관찰 2. 배선 대기 중인 추상화들 (삭제❌ → 연결 로드맵)
프로덕션 경로에 아직 연결 안 됐지만, "교체 가능성/개념 학습" 목적상 **존재 자체가 의도된 것**:
| 추상화 | 현재 | 첫 연결 지점(제안) |
|---|---|---|
| `LangChainLLMAdapter` | 정의·테스트만 | LangChain 체인/툴 호출이 필요한 워크플로우 도입 시 |
| `LangChainRetrieverAdapter` | 정의·테스트만 | LangChain `Retriever` API를 요구하는 컴포넌트 연결 시 |
| `Reranker`/`NoopReranker` | retriever와 분리 | `BasicRetriever`에 주입(기본 noop) → 추후 cross-encoder 교체 |
| `Tracer` | Pipeline에서만 사용 | `rag_basic` 노드에 span 부착 + `Answer.trace`(`models.py:29`) 채우기 |

→ 권장: 각 추상화에 "TODO: 첫 연결 지점" 주석/이슈를 남겨 *학습 의도*를 코드에 드러내면, 미래의 자신과 합류자가 "왜 안 쓰는데 있지?"라고 오해하지 않는다.

### 🟠 관찰 3. `create_chat_llm` — 이건 추상화를 *깨뜨린다* (수정 권장)
- `create_chat_llm`(`shared/llm/factory.py:15-21`)은 `shared/` 안에서 `langchain_anthropic.ChatAnthropic`를 import해
  **LangChain 구체 객체를 그대로 반환**한다. 같은 파일 `create_llm`이 추상 `LLMClient`를 반환하는 것과 대비된다.
- 이는 "추상화 선호" 철학과 **정면으로 어긋난다** — factory가 교체 가능한 추상 타입이 아니라 특정 구현 타입을 외부로 흘린다.
- 변환이 필요하다면 그 책임은 `adapters/`(아키텍처가 명시한 경계)에 둬야 한다.
  → 살릴 때 `LLMClient` + `LangChainLLMAdapter` 경유로 바꾸면, 위의 "배선 대기" 어댑터가 자연스럽게 첫 사용처를 얻는다.

### 🟡 관찰 4. 문서가 실제 추상화를 과소 기술한다
Loader·Chunker는 Indexer가 **필수로 의존**하는데(`indexer.py:1-3, 20-26`) 다이어그램에 없다.
학습용 지도라면 가장 먼저 배워야 할 인덱싱 파이프라인의 절반이 빠진 셈이다. Observability·orchestrator 추상도 누락.

---

## 4. 더 나은 구조 제안 (개정 다이어그램)

추상화를 **유지·확장**하는 방향. 핵심은 "문서가 실제 추상화 전부를 담고, 추상↔구체 관계를 드러내기".

```
shared/                       # 추상 역할 (ABC) + 교체 가능한 구현체
├── Model        ← 데이터 구조
├── Config       ← 환경변수 → 설정값
│
├── 【인덱싱 파이프라인】
│   ├── Loader       ← 원문 적재        (문서에 추가)
│   ├── Chunker      ← 문서 → 청크       (문서에 추가)
│   ├── Embedder     ← 텍스트 → 벡터
│   └── Indexer      ← 위 셋 + Store 조립
│
├── 【질의 파이프라인】
│   ├── Retriever    ← 질의 → 유사 청크
│   └── Reranker     ← 재정렬(현재 noop) → Retriever에 주입 (문서에 추가)
│
├── 【외부 의존 추상화】 ABC ← 구현체 ← Adapter
│   ├── LLM          ← Anthropic/OpenAI │ Adapter: LangChain 호환
│   └── VectorStore  ← PostgreSQL         │ Adapter: LangChain 호환
│
├── 【오케스트레이션 추상】 Pipeline/Step/Context   (문서에 추가)
│        ↑ 개념 모델. graphs/가 이를 LangGraph로 구현(추상↔구체)
│
└── 【횡단 관심사】 Observability                   (문서에 추가)
    ├── Tracer   ← 노드 span (rag_basic에 배선 예정)
    ├── Cache    ← LLM/Embedder 캐시
    └── Eval     ← Evaluator + metrics

graphs/                       # 구체 오케스트레이션 (LangGraph 구현)
└── rag_basic (StateGraph)    ← retrieve → generate
    └── Prompt                ← 워크플로우 자체 관리 (인라인 → 추출 권장)
```

**핵심 변경**
1. 다이어그램에 Loader/Chunker/Reranker/Observability/오케스트레이션 추상을 **추가** — 문서 = 코드.
2. `shared/orchestrator`(추상) ↔ `graphs/`(LangGraph 구체) 관계를 **추상↔구체 한 쌍**으로 명시.
3. 각 외부 의존 역할을 `ABC ← 구현체 ← Adapter` 3층으로 표기해 "교체축"을 시각화.

---

## 5. 실행 항목 (우선순위) — 삭제 없음, 정합성·배선 중심

| 우선순위 | 항목 | 근거 |
|---|---|---|
| **P1** | `architecture-roles.md`에 Loader/Chunker/Reranker/Observability/orchestrator 추가, Orchestrator를 `graphs/`로 명시 | §3 관찰4, §4 |
| **P1** | `shared/orchestrator`(추상) ↔ `graphs/`(구체) 관계 한 줄 정의 + `Context`/`RagState` 중복 처리 방침 합의 | §3 관찰1 |
| **P2** | `create_chat_llm`을 `LLMClient`+`LangChainLLMAdapter` 경유로 수정 (추상화 누수 제거) | §3 관찰3 |
| **P2** | `Reranker`를 `BasicRetriever`에 주입(기본 noop) — 교체축 실효화 | §3 관찰2 |
| **P3** | `Tracer`를 `rag_basic` 노드에 배선 + `Answer.trace` 채우기 | §3 관찰2 |
| **P3** | 배선 대기 추상화(어댑터 등)에 "첫 연결 지점" TODO 주석 — 학습 의도 명시 | §3 관찰2 |
| **P3** | `generate_node` 인라인 프롬프트를 `graphs/prompts.py`로 추출 | §2 |

> 판단 기준(이 프로젝트): 추상화는 **개념 학습 + 교체 가능성**을 위해 유지한다.
> 미연결 추상화는 "삭제"가 아니라 "**첫 연결 지점을 명시**"로 다룬다.
> 단, 추상화를 *깨뜨리는* 코드(`create_chat_llm`)는 철학에 맞게 바로잡는다.
