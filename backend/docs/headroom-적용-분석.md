# Headroom(`llms.txt`) 적용 분석

> 분석 대상: <https://github.com/chopratejas/headroom/blob/main/llms.txt>
> 작성일: 2026-06-02 · 상태: ⚪ 탐색/제안 (정식 채택 시 ADR 필요)

## 0. 먼저: 이 `llms.txt`가 가리키는 게 뭔가

`llms.txt`는 **Headroom**이라는 도구의 "AI가 읽는 랜딩 페이지"다. 따라서 "이 `llms.txt`를 적용하고 싶다"는 사실상 **Headroom을 도입하고 싶다**는 의미로 읽힌다.

**Headroom = LLM 컨텍스트 최적화 레이어.**
- 도구 출력·로그·파일·RAG 청크를 **모델에 도달하기 전에 압축**한다.
- "같은 답, 토큰 60–95% 절감"을 표방. JSON/코드/로그/diff/텍스트별 전용 압축기.
- **CCR(Compress-Cache-Retrieve)**: 원본을 지우지 않고 캐시 → LLM이 필요하면 원본을 되불러옴 (압축이 가역적).
- 배포 형태 4가지: ① Python/TS **라이브러리**(`headroom-ai`), ② **HTTP 프록시**(OpenAI/Anthropic 호환), ③ **MCP 서버**(`headroom_compress`/`headroom_retrieve`/`headroom_stats`), ④ 에이전트 래퍼(`headroom wrap claude` 등).
- Apache 2.0, **local-first, 기본 무(無)텔레메트리** → 사내 문서 다루는 우리 프로젝트 성격과 잘 맞음.

사용자가 말한 두 가지 의미는 Headroom의 두 배포 형태에 정확히 대응한다:
- **의미 1 (지금 Claude Code 세션)** → MCP 서버 / `headroom wrap claude` / 프록시.
- **의미 2 (작업 중 프로젝트)** → Python 라이브러리 / LangChain 통합 / 프록시.

> 참고로 `llms.txt`는 "AI 친화적 문서 색인"이라는 **별도의 관례**이기도 하다. Headroom 도입과 무관하게 우리 레포에도 `llms.txt`를 둘 수 있다 → §4에서 짧게 다룸.

---

## 1. 의미 1 — 지금 Claude Code 세션에 적용

### 무엇을 하나
Claude Code 세션의 토큰 소모 대부분은 **도구 출력**(파일 읽기, `grep`, `bash` 로그, 긴 diff)이 컨텍스트를 채우는 데서 온다. Headroom을 세션 앞단에 끼우면 이 출력들이 모델에 닿기 전 압축된다.

### 적용 경로 (난이도 순)

| 방법 | 명령 | 동작 | 비고 |
|---|---|---|---|
| **에이전트 래퍼** | `headroom wrap claude` | claude CLI를 프록시로 감싸 도구 출력/컨텍스트 자동 압축 | 가장 손쉬운 "자동" 경로. 단 Claude Code 호환 여부는 실측 확인 필요 |
| **MCP 서버** | `claude mcp add`로 `headroom_compress`/`retrieve`/`stats` 등록 | 모델이 **명시적으로** 압축/복원 도구를 호출 | 자동이 아니라 "모델이 부를 때"만. 큰 산출물을 의도적으로 압축할 때 |
| **로컬 프록시** | `headroom proxy --port 8787` 후 클라이언트가 `127.0.0.1:8787` 바라보게 | 모든 모델 트래픽이 프록시 경유 | API 호출을 우회시킬 수 있는 환경에서 |

설치: `pip install headroom-ai` (또는 `docker run ghcr.io/chopratejas/headroom:latest`).

### 기대 효과
- 같은 작업을 **더 적은 토큰/비용**으로, 컨텍스트 윈도우를 덜 채워 더 오래 끌고 감.
- CCR 덕에 압축돼도 모델이 원본을 되불러올 수 있어 정보 손실 위험이 낮음.

### 주의
- 세 번째 도구가 **모든 모델 트래픽을 가로채는** 구조 → 신뢰 검토 필요. 다만 local-first·무텔레메트리라 사내 환경에서도 비교적 안전.
- `wrap`/MCP의 Claude Code 실제 호환성·효과는 **소규모 세션에서 먼저 실측**하고 판단할 것 (벤치 수치는 공급자 주장).
- 이건 **순수 개인 워크플로우 개선**이라 프로젝트 코드/ADR과 무관 — 가볍게 시도해보고 효과 없으면 빼면 됨.

---

## 2. 의미 2 — `company-rag` 프로젝트에 적용

우리 프로젝트는 **LangGraph RAG 챗봇**이고, Headroom이 노리는 "토큰 많이 먹는 컨텍스트"가 코드 곳곳에 있다. 접목 지점을 가치/위험 순으로 정리한다.

### 접목 지점 지도

| 위치 | 현재 코드 | Headroom 적용 | 가치 | RAG 품질 리스크 |
|---|---|---|---|---|
| **에이전트 도구 출력** | `app/graph/nodes/tool_executor.py` (지금은 Mock, 자율 도구 루프 정식화 예정) | 도구 결과(JSON/표/로그) 압축 — SmartCrusher가 가장 강한 영역(70–95%) | ★★★ | 낮음 |
| **SQL 게이트 결과** | `sql_execute.py` (현재 브랜치 작업) | 큰 결과 테이블을 JSON/배열 압축 | ★★★ | 낮음 |
| **RAG 컨텍스트** | `generate_node`의 `context = "\n\n".join(d.chunk.text ...)` (`generate.py:33`) | 청크를 프롬프트에 넣기 전 텍스트 압축 | ★★ | **높음** — 이미 검색·rerank로 추린 "정답 후보"라 압축이 답변/인용 정확도를 깎을 수 있음 |
| **LLM 클라이언트** | `core/llm/base.py`의 `LLMClient.complete()` / Anthropic 구현 | `withHeadroom(anthropic)` 래퍼 또는 프록시 경유 | ★★ | 전역 영향 → 신중 |

→ **가장 안전하고 효과 큰 진입점은 "에이전트 도구 출력 + SQL 결과" 압축.** RAG 청크 압축은 효과는 있으나 인용 충실도를 해칠 수 있어 후순위.

### 레이어 경계 (절대 위반 금지 — `backend/CLAUDE.md`)
- `core/`는 LangGraph 불가지. 노드(`app/graph/nodes/`)는 순수 함수, side effect는 `core/` 호출로만.
- 따라서 Headroom을 노드 안에 직접 박지 말 것. **`core/`에 압축 추상화를 두고 노드가 그걸 호출**해야 함.

권장 형태 (추상화 선호 피드백과도 정합 — 미연결이라도 ABC 보존):
```
core/context/
  base.py        # ContextCompressor(ABC): compress(text, kind) -> str / retrieve(ref)
  noop.py        # NoopCompressor — 기본값(아무것도 안 함)
  headroom.py    # HeadroomCompressor — headroom-ai 위임
  factory.py     # config/env로 구현체 선택
```
- 기본값은 **Noop**, env/`config`로 켤 때만 Headroom 활성 → 점진 도입 + 롤백 용이.
- 도구 출력/SQL 결과를 만드는 노드가 `core.context`를 통해 압축. RAG 경로는 나중에 별도 플래그로.

### 기대 효과
- 토큰/비용 절감 — 우리에겐 이미 `core/observability/cost_tracker.py`가 있으므로 **절감액을 그대로 계측** 가능.
- 자율 도구 루프(역기획서 §10, 다음 작업)에서 도구 출력이 누적돼 컨텍스트가 터지는 문제를 선제 완화.
- CCR로 원본 보존 → 인용/근거 추적성 유지.
- local-first·무텔레메트리 → FGA로 보호하는 사내 문서가 외부로 안 나감.

### 도입 시 반드시 (DoD)
1. **ADR 작성** — 새 의존성·패턴이므로 `backend/CLAUDE.md` DoD 규칙 3 해당. `docs/superpowers/decisions/ADR-NNNN-headroom-context-compression.md`.
2. **eval 회귀 확인** — `tests/eval/runner.py`로 압축 ON/OFF A/B. RAG 청크 압축을 켤 경우 답변·인용 점수 하락 여부 필수 검증 (DoD 규칙 2).
3. **단위 테스트** — `ContextCompressor` 구현체 + 노드 통합.
4. **수술적 변경** — 도구 출력 경로부터 좁게. 전역 LLM 래핑은 효과 확인 후.

### 리스크 요약
- **품질**: RAG 청크 압축은 "같은 답" 보장이 우리 도메인(정확 인용)에선 깨질 수 있음 → eval 게이트 통과 전 RAG 경로엔 적용 금지.
- **의존성**: `tree-sitter` 등 무거운 extra가 딸려올 수 있음 — `[all]` 말고 필요한 것만.
- **결합도**: 외부 라이브러리에 컨텍스트 파이프라인을 묶음 → ABC로 격리해 교체 가능성 유지.

---

## 3. 권장 로드맵

1. **(개인) 의미 1 먼저, 비용 0에 가깝게 실측** — `headroom wrap claude` 또는 MCP를 한 세션에 붙여보고 `headroom_stats`로 절감폭 확인. 효과 없으면 폐기.
2. **(프로젝트) PoC** — `core/context/` ABC + `NoopCompressor`만 먼저 머지(추상화 보존). 도구 출력/SQL 결과 경로에 호출부만 배선, 기본 Noop.
3. **HeadroomCompressor 구현 + env 플래그** → 도구 출력에만 켜고 `cost_tracker` + eval로 측정.
4. 측정 결과가 좋고 품질 무해하면 **ADR로 정식화**, 이후 RAG 경로 확대 여부 별도 판단.

---

## 4. 곁가지 — `llms.txt` 관례 자체를 우리 레포에도

Headroom과 별개로, `llms.txt`는 "AI 에이전트가 레포를 빨리 파악하도록 핵심 문서를 한 파일에 색인"하는 관례다. 우리도 둘 수 있다:
- `backend/llms.txt` 또는 루트 `llms.txt`에 README·`CLAUDE.md`·`DESIGN.md`·ADR 인덱스·langgraph-guide 링크를 한 줄 설명과 함께 색인.
- 이미 `CLAUDE.md`/`docs/.../README.md`(ADR 자동 인덱스)가 그 역할을 일부 하므로 **중복 최소화**가 관건. 외부 에이전트/툴이 레포를 소비할 일이 생기면 그때 추가하는 게 합리적.

---

## 부록 — 출처
- `llms.txt` 원문(2026-06-02 fetch): Headroom = "Context optimization layer for LLM applications… 60–95% fewer tokens. Library, proxy, and MCP server. Apache 2.0, local-first."
- 우리 측 접목 근거: `app/graph/nodes/generate.py:33`(RAG 컨텍스트 조립), `app/graph/nodes/tool_executor.py`(도구 출력), `app/graph/nodes/sql_execute.py`(SQL 결과), `core/llm/base.py`(LLM 추상화), `core/observability/cost_tracker.py`(절감 계측).
