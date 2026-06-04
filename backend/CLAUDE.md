# 프로젝트 안내 (Claude Code용)
> CLAUDE.md에 내용 추가 시, 상세 내용은 별도 파일로 분리하고 경로 참조만 남긴다. 본문에는 hard constraint와 판단 기준만 유지한다.

## 프로젝트 개요
LangGraph 기반 RAG 챗봇. Python 3.11+, `langgraph` + `langchain-anthropic`.

## 참조 문서
- LangGraph 설계/구현 질문 → **먼저 `docs/langgraph-guide/INDEX.md`**. ADR과 어긋나는 패턴 제안 시 거부하거나 ADR 갱신 PR 먼저 제안할 것.
- ADR 목록 → `docs/superpowers/decisions/`

## 레이어 경계 (절대 위반 금지)
- `core/`는 LangGraph를 모른다. import 금지.
- `app/`는 `core/`의 인터페이스(ABC)만 의존. 구현체 직접 참조 금지.
- `app/graph/nodes/`는 순수 함수. State in → State out. side effect는 `core/` 호출로만.

## 핵심 아키텍처 결정
- State: `AgentState(TypedDict)`. `MessagesState` 및 임의 dict 금지.
- 라우터: `router_node` — `route` 필드로 doc_search/agent 분기 (`app/graph/nodes/router.py`)
- HITL: `interrupt()` — (1) agent 도구 호출 경로(`confirm.py`), (2) 라우터 모호 분기(`clarify.py`). `MemorySaver` checkpointer 필수. (ADR-0042)
- FGA: 폴더 트리 pre-filter. `ListObjects(can_read, folder)`로 읽을 수 있는 폴더 목록을 받아, 그 폴더에 정확 매칭(`path = ANY`)되는 청크만 검색(prefix 확장 안 함 — private 하위 누수 방지). 권한 주체는 부서(department) 단위 — 개인 단위 메타데이터·sensitivity 없음. 상세: ADR-0015.
- FGA 캐시: PostgreSQL TTL 캐시 (Redis 미사용).
- 부서 멤버십 source of truth: **OpenFGA** (`user:X member department:Y` 튜플). `config/users.yaml`은 부트스트랩 시드 입력일 뿐(`scripts/seed_fga.py`, 멱등·일방향), 운영 중 멤버 추가/제거는 OpenFGA 직접 조작(관리자 API `add/remove_department_member` 또는 `manage_permission` 도구)으로만. PostgreSQL은 멤버십 미저장(캐시·감사 로그만).
- SQL 도구 쓰기: 읽기=sql_tool_ro, 게이트 통과한 쓰기(UPDATE/DELETE)=sql_tool_rw 이중 계정. WHERE 필수. 상세: ADR-0034.
- 권한 위임: 부서 관리자(`user:X admin department:Y`)는 자기 부서 **멤버십만** 위임(grant/revoke). `dept_viewer`·capability 부여는 전역 c_level 전용(경계 누수 차단). 게이트는 `tool_gate_node`가 `gate_decision` 위에 합성. 상세: ADR-0046.
- 테이블별 SQL 접근: `type table`의 `can_access`로 `table:employees`/`table:sales` 단위 하드 게이트. 위험도 게이트(capability:sql)와 **AND** — 참조 테이블 접근권 미보유 시 실행 전 DENY. 상세: ADR-0047.
- 명명 원칙: 외부 경계 노출 이름은 역할(role), 내부 구현은 how 허용(캡슐화). 상세: ADR-0033.

## 작업 규칙
1. **새 노드/엣지 추가 전**: `docs/langgraph-guide/INDEX.md` 먼저 읽기.
2. **상태 스키마 변경**: `AgentState(TypedDict)` 확장만. 임의 dict 금지.
3. **외부 API 호출 노드**: retry + timeout 필수.
4. **테스트**: 노드는 순수 함수로 작성해 단위 테스트 가능하게.
5. **`core/` 추상화**: ABC·미연결 구현체 삭제 제안/실행 금지. 학습 목적 + 구현체 교체 가능성 유지.
6. **수술적 변경**: 요청에 해당하는 줄만 수정. 인접 코드·주석·포맷 수정 금지. 기존 스타일 유지. 내 변경이 만든 dead code만 정리.

## 코딩 원칙 (Karpathy 4원칙)
상세: `docs/superpowers/decisions/ADR-0010-karpathy-guidelines-audit.md`

1. **먼저 생각하라**: 구현 전 가정 명시. 불확실하면 질문.
2. **단순함 우선**: 요청한 것만 구현. 추측성 기능·추상화 금지. (`core/` 예외: 규칙 5)
3. **수술적 변경**: 요청에 해당하는 줄만. (규칙 6 참조)
4. **목표 중심**: 멀티스텝 착수 전 "단계 → 검증" 명시.

## 결정 기록 규칙
`AskUserQuestion`으로 설계·방향·도구 선택 발생 시 즉시 ADR 생성.
경로: `docs/superpowers/decisions/ADR-NNNN-<topic>.md` (NNNN = 날짜순 일련번호, 기존 최대값+1) / 템플릿: `docs/superpowers/decisions/_template.md`
- **Status 배지**: 모든 ADR은 제목 바로 아래 `> **Status**: <배지>` 한 줄을 둔다. 어휘(6단계): 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기. 대체됨은 `→ [ADR-NNNN](...)` 링크 포함.
- **인덱스 자동 갱신**: ADR을 추가하거나 상태를 바꾼 뒤 `python -m scripts.gen_adr_index` 실행 → `decisions/README.md` 재생성. README는 자동 생성물이니 직접 편집하지 않는다.

## DoD (Definition of Done)
1. 단위 테스트 추가
2. `tests/eval/runner.py`로 회귀 점수 확인 (하락 시 원인 명시)
3. 새 의존성·패턴 도입 시 ADR 작성 및 CLAUDE.md ADR 섹션 갱신

## Phase 작업 워크플로우
1. `git checkout -b feat/phase-N`
2. 작업 및 커밋
3. PR 생성 — description에 DoD 체크리스트 포함 (`plan/plan.md` DoD 항목 기준)
4. merge 후 태그: `git tag phase-N && git push origin phase-N`

> Phase 1~5 완료. Phase 1=e6c2124, Phase 2=954a693
