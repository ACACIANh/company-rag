# Tool 영역 추가 작업

기존 RAG 구조에 Tool 영역을 추가한다. 순수 RAG는 그대로 두고, Tool 사용은 별도 Agentic 워크플로우로 분리한다.

## 추가 구조

```
shared/
└── tool/
    ├── spec.py          # ToolSpec: LLM에게 노출되는 스키마 (name, description, params)
    ├── registry.py      # Tool 등록·조회
    ├── base.py          # ReadOnlyTool, MutatingTool 추상 클래스
    ├── policy.py        # 권한·승인·rate limit·감사 로그
    └── adapters/        # Slack, Mail, DB(read/write), Cache 등

workflows/
└── agentic/
    ├── orchestrator.py  # Tool 선택·호출 루프
    ├── executor.py      # Tool 실제 호출 + 결과 정규화
    └── prompt/
```

## 핵심 원칙

**1. Read와 Write를 타입으로 분리**
- `ReadOnlyTool`: DB 조회, 캐시 조회 등 — 자유 호출, 멱등
- `MutatingTool`: Slack/메일 발송, DB 쓰기 등 — Policy 통과 필수

타입을 분리하지 않으면 LLM이 실수로 메일 100통 보내는 사고가 가능하다.

**2. Tool은 shared, Agent 루프는 workflows**
Tool 자체는 재사용 자원이라 `shared/`에, "어떤 Tool을 언제 쓸지 결정하는 루프"는 `workflows/agentic/`에 둔다. 순수 RAG(`workflows/qa/`)는 Tool을 모른다.

**3. ToolSpec과 구현 분리**
LLM에게는 스키마(`ToolSpec`)만 노출, 실제 구현 클래스는 숨긴다. OpenAI function calling / Anthropic tool use 포맷에 맞춰 정의.

**4. Retriever는 Tool로 만들지 말 것**
결정론적 RAG가 비결정적이 된다. Agentic 워크플로우에서 필요할 때만 `RetrieverTool` 어댑터로 감싸서 등록.

**5. Policy 레이어 처음부터 자리 잡기**
프롬프트 인젝션 방어의 핵심. 비어 있어도 좋으니 디렉토리·인터페이스는 1단계에 만든다.
- 권한 체크 / 파라미터 검증 / 승인 / rate limit / 감사 로그

## 작업 순서

1. `shared/tool/` 인터페이스·스키마 정의 (`ToolSpec`, `ReadOnlyTool`, `MutatingTool`, `ToolRegistry`)
2. `policy.py` 스켈레톤 (실제 로직은 나중에)
3. 어댑터 2개로 검증: `DbQueryTool`(read), `SlackTool`(write)
4. `workflows/agentic/` 오케스트레이터 + 익스큐터
5. end-to-end 동작 확인