# 설계: 도구 라벨 자동 표시 + capability 응답 감사 요약

> 작성일: 2026-06-05
> 상태: 승인됨 (구현 계획 작성 대기)

## 배경 / 목표

두 가지 사용자 요구사항:

1. **요청 1**: 최초 질문이 capability 로직(권한 기능 안내)을 탈 때, **관리자**에게는 감사로그 **건수 요약**도 함께 보여준다.
2. **요청 2**: 응답 시 어떤 도구(`rag` / `sql` / `permission` / `audit`)를 사용했는지 **답변 상단 헤더**에 라벨로 표시한다.

추가 제약(사용자 명시): 라벨 매핑은 도구가 늘어날 때마다 수동으로 매핑 테이블을 늘리는 구조가 아니라, **스프링 컴포넌트 스캔처럼 자동으로 발견·전파**되는 구조여야 한다. 도구 레지스트리를 단일 진실원천(SSOT)으로 삼는다.

## 현재 구조 (조사 결과)

- 응답: 그래프 실행 → `Answer(text, sources, trace)` (`core/models.py:31`) → API에서 `ChatResponse(answer, sources, session_id)` (`app/api/chat.py:131`). 스트리밍은 `sources` 이벤트에 `route` 동봉 (`app/graph/builder.py:322`).
- 도구 레지스트리: `build_tool_registry` (`app/graph/tools/registry.py:23`). 각 도구는 `ToolAgent` 프로토콜(`name`, `plan`, `execute`) 구현 (`app/graph/tools/base.py:10`).
  - `SqlAgent`(name=`query_business_data`), `PermissionAgent`(name=`manage_permission`), `AuditAgent`(name=`audit_history`).
- 도구 호출 추적: `AgentState.agent_messages`(`add_messages`)에 `AIMessage.tool_calls` 누적 (`app/graph/state.py:36`).
- capability 경로: `router_node` → `capability_node`(`app/graph/nodes/capability_node.py:30`). 현재 `can_grant`(admin) 여부로 안내 텍스트만 반환, `citations=[]`.
- 감사로그: `gate_audit_log` 테이블(append-only), `PostgresAuditSink` (`core/observability/audit/postgres_sink.py:16`), `AuditRecord`에 `gate_decision`(ALLOW/DENY/JUSTIFY_AND_APPROVE) 포함 (`core/observability/audit/base.py:11`). 조회 도구 `AuditAgent` (`app/graph/tools/audit_history_tool.py`).
- 프론트: `ChatMessage`(`web/src/types.ts:40`), 출처는 `SourceBadge`(`web/src/chat/SourceBadge.tsx`)로 답변 아래 칩. 스트림 핸들러 `web/src/chat/ChatPage.tsx:84`.

## 설계

### 요청 2 — 도구 라벨 자동 발견 + 상단 헤더 표시

#### 백엔드

1. **`ToolAgent` 프로토콜에 `label: str` 추가** (`app/graph/tools/base.py`). 각 도구가 자기 역할 라벨을 스스로 선언한다.
   - `SqlAgent.label = "sql"`
   - `PermissionAgent.label = "permission"`
   - `AuditAgent.label = "audit"`
2. **레지스트리가 `name → label` 맵을 함께 노출** (`registry.py`). `build_tool_registry`가 등록된 도구들로부터 맵을 자동 수집하여 반환(또는 레지스트리 객체에 포함). 수동 매핑 테이블 없음.
3. **호출된 도구 라벨 계산** (app 레이어, 그래프 실행 후 응답 조립부):
   - `agent_messages`를 순회하며 `AIMessage.tool_calls`의 도구 `name`들을 수집(중복 제거, 호출 순서 보존).
   - 레지스트리 맵으로 `name → label` 변환.
   - `route == "doc_search"`이면 `rag` 라벨을 부여(RAG는 `ToolAgent`가 아니라 라우트라서 이 한 곳에서만 매핑).
   - `route == "capability"`(권한 안내)는 도구를 호출하지 않으므로 헤더 라벨 없음(요약은 본문에 — 요청 1).
4. **응답 스키마에 `tools: list[str]` 추가**:
   - `core/models.py` `Answer`에 `tools: list[str] = field(default_factory=list)` (범용 문자열 리스트라 레이어 경계 무해).
   - 비스트리밍 `ChatResponse`(`app/api/chat.py`)에 `tools: list[str]` 추가, `result.tools`로 채움.
   - 스트리밍 `sources` 이벤트(`builder.py`)에 `tools` 필드 추가.

> **자동 전파 보장**: 새 도구 추가 = 레지스트리 등록 + `label` 선언. 그러면 라벨이 응답 스키마와 프론트 헤더까지 코드 수정 없이 자동으로 흐른다.

#### 프론트엔드

- `ChatMessage` 타입(`web/src/types.ts`)에 `tools?: string[]` 추가.
- `ChatPage` 스트림 핸들러(`ChatPage.tsx`)가 `sources` 이벤트에서 `tools` 수신하여 메시지에 저장.
- 답변 **상단 헤더**에 `🔧 도구: sql · audit` 형태로 렌더링. 도구 0개면 헤더 미표시. (`MessageList` 인라인 또는 소형 `ToolHeader` 컴포넌트; 기존 `SourceBadge` 칩 스타일과 일관성 유지.)

### 요청 1 — 관리자 capability 응답에 감사로그 건수 요약

#### 백엔드

1. **`AuditSink` ABC에 집계 메서드 추가** (`core/observability/audit/base.py`): `count_by_decision()` → `{ "ALLOW": n, "DENY": n, "JUSTIFY_AND_APPROVE": n }` 형태(또는 total 포함). `PostgresAuditSink`에 `SELECT gate_decision, COUNT(*) FROM gate_audit_log GROUP BY gate_decision` 구현.
2. **`capability_node`에 `audit_sink` 의존성 주입** (builder의 노드 바인딩 지점). 기존 `can_grant`(admin)일 때만 집계를 조회하여 안내 텍스트 뒤에 요약 한 줄을 덧붙인다.
   - 예: `📊 최근 게이트 결정: 총 23건 (ALLOW 15 · DENY 3 · JUSTIFY 5)`
   - 비admin(`can_grant=False`)은 기존과 동일(요약 없음).

## 레이어 경계 점검

- `Answer.tools`, `count_by_decision`는 모두 core/의 범용 추상(문자열/숫자)만 다룬다 — LangGraph 불가지 유지.
- `name → label` 매핑과 route→tools 계산은 app 레이어에서 수행(레지스트리는 app 소속).
- `capability_node`는 `AuditSink` ABC에만 의존(구현체 직접 참조 금지).

## 검증 계획

- 단위 테스트
  - `PostgresAuditSink.count_by_decision` 집계 정확성.
  - 레지스트리 `name → label` 맵 생성.
  - route + agent_messages → tools 라벨 변환(doc_search→rag, agent 다중 도구, 중복 제거/순서).
  - `capability_node` admin/비admin 분기(요약 유무).
- 프론트: 도구 헤더 렌더링, 도구 0개 시 미표시.
- `tests/eval/runner.py` 회귀 점수(하락 시 원인 명시).
- ADR 작성: (a) 도구 라벨 자동 발견 구조, (b) capability 감사 요약. CLAUDE.md ADR 섹션 갱신.

## 확정된 결정 사항

- 감사로그 대상: **관리자에게만**.
- 감사로그 형식: **건수 요약만**.
- 라벨 표시 위치: **답변 상단 헤더**.
- 라벨 매핑: **레지스트리 SSOT 자동 발견**(도구 self-declare `label`).
- capability 라우트: 도구 헤더 라벨 **미표시**(본문에 요약만).

## 범위 외 (YAGNI)

- 감사로그 상세 목록/필터 UI(기존 `audit_history` 도구로 충분).
- 도구별 아이콘/색상 테마(텍스트 라벨로 시작).
- 라벨 다국어/i18n.
