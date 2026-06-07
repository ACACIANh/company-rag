# 데모 영상 녹화 하니스 설계 (Playwright)

> **Status**: ⚪ 제안됨

## 배경 / 목적

비즈니스 관계자용 15장면 데모(올드보이 테마)를 **Playwright로 웹 UI를 자동 조작하며 단일 연속 영상으로 녹화**한다. 사람 손 없이 일관된 데모 영상을 재생산하고, "권한 통제 스토리"를 영상만으로 전달한다.

- 영상 초점: **권한 통제 스토리** (권한 노출 → 차단 → 통제(JUSTIFY/DENY) → 부여 → 감사추적 → 즉시반영 → 부서위임 before/after)
- 범위: **15장면 전부** (먼저 풀로 찍어보고 길이/구성 판단)
- 결과물: **단일 연속 영상 1개** (webm)
- 예상 길이: raw 약 4~6분 (LLM 대기 포함). 벤치 기준 순수 LLM 응답 합계 중앙값 ~86초(baseline) + 타이핑·읽기 텀·계정 전환·HITL.

## 핵심 결정 (브레인스토밍 합의)

| 항목 | 결정 |
|------|------|
| 녹화 도구 | Playwright **라이브러리**(plain script, test 러너 아님) + 단일 제어 스크립트 |
| 장면 범위 | 15장면 전부 |
| 캡션 | 하니스가 **인라인 캡션 오버레이를 DOM에 자동 주입** (장면 시작 fade-in 후 유지) |
| 출력 | 단일 연속 webm 1개 |
| 실행 전제 | 백엔드(8000)·프론트(5173)는 **사용자가 미리 기동**. 하니스는 `demo_reset` + 녹화만 담당 |
| 시나리오 SSOT | `demo_bench.py`의 `SCENES`가 단일 원천. `--export-scenes`로 JSON 추출 → TS 하니스가 소비 (중복 정의 없음) |
| selector 전략 | 한글 텍스트·role·속성 기반. 프론트는 **수술적 변경 원칙상 미변경**(깨지면 후속으로 `data-testid` 추가) |
| 페이싱 기본값 | 질문 타이핑 글자당 ~40ms, 응답 완료 후 읽기 텀 2~3초, 캡션 fade-in 후 장면 동안 유지 |

## 아키텍처

```
backend/scripts/demo_bench.py   ──(--export-scenes <path>)──▶  scenes.json (생성물, SSOT 파생)
backend/scripts/demo_reset.py   ──(하니스가 subprocess 호출)

web/demo-recorder/
├── record-demo.ts        # 오케스트레이터(진입점)
├── captions.ts           # kind→설명 문구 매핑 + 장면별 오버라이드 (영상 전용 데이터)
├── lib/
│   ├── auth.ts           # 로그인/로그아웃·계정 전환
│   ├── chat.ts           # 질문 타이핑·전송·응답완료 대기
│   ├── hitl.ts           # JUSTIFY 사유입력·승인, clarify 옵션선택
│   └── overlay.ts        # 캡션 DOM 주입·fade
└── out/demo-<timestamp>.webm   # 결과물
```

- `web/`에 `playwright`(라이브러리)를 devDependency로 추가.
- export JSON 스키마: `{ id, account, display_name, dept, question, kind, resume_text }`
  - `display_name`/`dept`는 `demo_bench.py`가 `users.yaml`을 조인해 채운다(캡션·계정 전환용).

## 데이터: SCENES 원천 (demo_bench.py)

15장면 정의 (account는 `users.yaml`의 username과 일치):

| id | account | display_name | kind | resume_text(HITL) |
|----|---------|--------------|------|-------------------|
| 01 | daesu | 오대수(인사) | capability | — |
| 02 | daesu | 오대수(인사) | permission | — |
| 03 | daesu | 오대수(인사) | rag | — |
| 04 | daesu | 오대수(인사) | clarify | "사내 문서 검색 (RAG)" (옵션선택) |
| 05 | daesu | 오대수(인사) | rag_block | — |
| 06 | daesu | 오대수(인사) | sql_read | "감사 대비 인사 데이터 확인 목적입니다." (JUSTIFY) |
| 07 | daesu | 오대수(인사) | sql_write_deny | — |
| 08 | admin | 이우진 | sql_read | "유휴 장비 재고 확인 목적입니다." (JUSTIFY) |
| 09 | admin | 이우진 | sql_write | "신규 입사자 장비 지급 처리입니다." (JUSTIFY) |
| 10 | admin | 이우진 | permission | "권한 부여를 승인합니다." (JUSTIFY) |
| 11 | admin | 이우진 | audit | — |
| 12 | daesu | 오대수(인사) | rag | — |
| 13 | mido | 미도(제품) | permission | — (위임 전 before) |
| 14 | joohwan | 노주환(개발) | permission_delegate | "팀 재배치에 따른 개발팀 합류 처리입니다." (JUSTIFY) |
| 15 | mido | 미도(제품) | permission | — (위임 후 after) |

**HITL 분기 판별**: `resume_text`가 `null`이 아니면 interrupt 처리.
- `kind == "clarify"` → ClarifyCard 옵션 클릭
- `kind in {sql_read, sql_write, permission, permission_delegate}` (resume_text 존재) → JUSTIFY 사유입력 → 전송

## 실행 흐름 (단일 명령)

1. 하니스가 `demo_bench.py --export-scenes web/demo-recorder/scenes.json` 실행 → SSOT 동기화
2. 하니스가 `demo_reset.py` subprocess 호출 → 깨끗한 데모 상태
3. Chromium 실행 → `browser.newContext({ recordVideo: { dir, size } })` (단일 컨텍스트)
4. 15장면 순차 재생:
   - 직전 장면과 `account`가 다르면 로그아웃 → 로그인
   - 캡션 오버레이 fade-in (`장면 {id} · {display_name} · {설명}`)
   - 질문 타이핑(~40ms/char) → 전송
   - `kind` 분기 상호작용(위 표)
   - "답변 생성 중…" 사라질 때까지 대기(장면당 최대 60초) → 읽기 텀 2~3초 → 캡션 fade-out
5. `context.close()` (finally) → webm 저장 → `out/demo-<timestamp>.webm`로 rename

## UI Selector 참조 (현 프론트 기준, data-testid 없음)

| 요소 | selector |
|------|----------|
| 로그인 ID 입력 | `input[autocomplete="username"]` |
| 로그인 비밀번호 입력 | `input[type="password"]` |
| 로그인 버튼 | `button[type="submit"]` (text "로그인") |
| 로그아웃 버튼 | `button:has-text("로그아웃")` (헤더) |
| 채팅 입력 | `textarea` (placeholder "질문을 입력하세요…") |
| 전송 버튼 | `button:has-text("전송")` |
| 로딩 인디케이터 | `text="답변 생성 중…"` (사라짐 = 응답 완료) |
| JUSTIFY 카드 | `div:has-text("실행 승인이 필요합니다")` |
| JUSTIFY 사유입력 | `textarea` (placeholder "실행 사유를 입력하세요") |
| clarify 옵션 버튼 | `button:has-text("<옵션 라벨>")` (resume_text와 일치) |

- 토큰 저장: `localStorage["token"]`. 계정 전환은 로그아웃(토큰 제거) 후 재로그인.
- dev 서버 포트 5173, API base `http://localhost:8000` (`VITE_API_BASE_URL`).

## 캡션 데이터 (captions.ts)

`scenes.json`엔 연출용 설명이 없으므로 하니스가 보유:
- `kind` → 기본 문구 매핑 + 장면별 오버라이드(필요 시).
- 포맷: `장면 {id} · {display_name} · {설명}`.
- 연출 텍스트라 Python SSOT(`SCENES`)와 분리(영상 전용 관심사).

## 에러 처리

- **Fail-fast**: selector 미발견·타임아웃 시 즉시 중단, "장면 {id}에서 실패: <이유>" 출력. 깨진 영상을 계속 생성하지 않음.
- `context.close()`는 `finally`에 두어 중단 시에도 부분 영상 저장(디버깅용).
- interrupt 기대 장면(`resume_text`≠null)에서 카드가 안 뜨면 명확히 경고 후 중단.
- 외부 API 호출(LLM) 특성상 장면당 타임아웃 60초.

## 테스트 (DoD)

하니스는 실 브라우저·LLM 통합이라 E2E 단위 테스트 부적합. **순수 로직만 Vitest로**:
1. `captions.ts` — 캡션 문자열 생성(포맷·오버라이드)
2. 계정 전환 판단 — "직전 account와 다르면 재로그인"
3. `kind` → 상호작용 분기 매핑 (clarify / JUSTIFY / plain)

selector·페이싱·녹화 정상 동작은 **실제 1회 실행으로 검증**("찍어보고 판단" 단계).

## 비범위 (YAGNI)

- 장면별 분할 클립, 음성 내레이션/TTS, 자동 배속·대기 컷 편집 → 후처리는 사용자 몫.
- 서버 자동 기동·프로세스 관리(사용자가 미리 기동).
- 영상 길이 최적화를 위한 장면 솎아내기 → 풀 녹화 후 판단.

## 후속 가능 과제

- selector가 자주 깨지면 프론트 컴포넌트에 `data-testid` 추가(별도 PR).
- 첫 녹화 후 페이싱(타이핑 속도·읽기 텀) 튜닝.
- 권한 서사 라인 중심 8~10장면 축약본(필요 시).
