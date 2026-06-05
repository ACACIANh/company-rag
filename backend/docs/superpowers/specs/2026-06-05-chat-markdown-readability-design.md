# 채팅 응답 가독성 개선 — 마크다운 포맷 도입

## 목표

현재 권한 조회 응답이 plain text로 반환되어 사람이 읽기 어렵다.
`_format_permission_snapshot()`이 GFM 마크다운을 반환하도록 바꾸고,
에이전트 시스템 프롬프트에 마크다운 포맷 사용 지시를 추가한다.
프론트엔드는 기존 `MarkdownRenderer`(GFM + highlight.js)가 이미 렌더링을 처리하므로 스타일 미세 조정만 한다.

## 스코프 결정

- **인스코프**: 권한 조회 응답 (`manage_permission` 도구의 `query` 결과)
- **인스코프**: 에이전트 일반 응답 마크다운 지시
- **아웃스코프**: RAG 생성 응답, SQL 결과 포맷 변경 (별도 작업)

## 변경 상세

### 1. `app/graph/tools/permission_tool.py` — `_format_permission_snapshot()`

**현재 출력 (plain text):**
```
사용자: user-admin
소속 부서: (없음)
역할(role): c_level
접근 가능 폴더 10개:
  - /company
  ...
SQL/관리 권한:
  - SELECT: 즉시 허용
```

**변경 후 출력 (GFM 마크다운):**
```markdown
## 권한 스냅샷

| 항목 | 값 |
|------|-----|
| 사용자 | `user-admin` |
| 역할 | `c_level` |
| 소속 부서 | 없음 |

### 접근 가능 폴더 (10개)
- `/company`
- `/company/common`
...

### SQL / 관리 권한

| 작업 | 허용 여부 |
|------|----------|
| SELECT | ✅ 즉시 허용 |
| 대량 SELECT | ⚠️ 사유 기재 후 허용 |
| UPDATE / DELETE | ⚠️ 사유 기재 후 허용 |
| DDL | ❌ 불가 |
| 권한 부여(grant) | ⚠️ 사유 기재 후 허용 |
```

- 결정 라벨 → 이모지 매핑: `즉시 허용` → `✅`, `사유 기재 후 허용` → `⚠️`, `불가` → `❌`
- 기존 `_DECISION_LABEL` dict는 유지, 별도 `_DECISION_EMOJI` dict 추가
- 폴더 목록은 bullet list 유지 (테이블보다 가독성 우세)
- `_format_permission_snapshot()` 시그니처·반환 타입 변경 없음 (`str` 반환)

### 2. `app/graph/nodes/agent.py` — `_SYSTEM` 프롬프트

한 줄 추가:
```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다. "
    "구조화된 정보(목록·비교·수치)는 마크다운 헤더·표·목록을 사용해 정리한다."  # ← 추가
)
```

### 3. `web/src/chat/MarkdownRenderer.tsx` — 스타일 조정 (소규모)

현재 테이블 셀(`td`)은 `max-w-[260px]`으로 너비가 제한되어 있다.
권한 테이블은 2열(작업·허용여부) 구조로 좁아서 현재 스타일로 충분할 수 있다.
렌더링 확인 후 필요 시 `max-w` 완화 또는 컬럼별 너비 고정.

구체적 변경이 필요한 경우:
- `th` 스타일: 현재 `text-[11px] font-semibold text-ink-mute` — 그대로 유지
- `td` 스타일: 이모지(✅⚠️❌)가 포함되어도 깨짐 없음 확인 후 확정

## 데이터 흐름

```
manage_permission.execute()
  → _format_permission_snapshot()  [마크다운 반환]
  → agent LLM ("마크다운 표 변형 없이 포함" 지시)
  → SSE token stream
  → MarkdownRenderer (GFM 렌더링)
  → 사용자 화면
```

## 테스트 계획

1. `test_format_permission_snapshot_markdown` 단위 테스트
   - 출력이 `## 권한 스냅샷` 헤더 포함 확인
   - 이모지 매핑 정확도 (즉시 허용→✅ 등)
   - 폴더 0개일 때 `(없음)` 처리 확인
2. 기존 통합 테스트(`tests/`) 회귀 없음 확인
3. 수동: 브라우저에서 권한 조회 응답 렌더링 확인

## 제약

- `_format_permission_snapshot()` 반환값은 `str`이므로 시그니처 변경 없음
- LLM이 마크다운을 수정하지 않도록 `_SYSTEM` 지시 강화 (기존 지시와 일관)
- 프론트엔드는 신규 컴포넌트 없음 — 기존 `MarkdownRenderer` 재사용
