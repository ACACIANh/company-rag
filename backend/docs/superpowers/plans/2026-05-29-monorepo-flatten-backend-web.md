# 모노레포 수평 구조 재편 (backend / web) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 루트에 흩어진 백엔드 전부를 `backend/`로 모으고 `shared/`를 `core/`로 리네임해, `web/`과 형제(수평) 관계의 모노레포 구조로 재편한다.

**Architecture:** 백엔드 경로 의존이 모두 cwd 상대경로이므로 `backend/`를 실행 루트로 삼으면 코드 경로 수정이 불필요하다. 유일한 코드 변경은 `shared`→`core` import 치환(117개 파일). 이동은 `git mv`로 이력을 보존하고, git 미추적 파일(`.env`, `.chroma`, `logs`)만 일반 `mv`로 옮긴다.

**Tech Stack:** git, bash/sed, Python 3.11+, pytest, Vite(영향 없음).

**참조 스펙:** `docs/superpowers/specs/2026-05-29-monorepo-flatten-backend-web-design.md`

---

### Task 0: 브랜치 생성 + baseline 캡처

이동의 정답지(baseline)를 먼저 확보한다. 이동 후 같은 결과가 나와야 성공이다.

**Files:** 없음 (환경 준비)

- [ ] **Step 1: 작업 브랜치 생성**

Run:
```bash
cd /Users/acacian/vscode/company-rag
git switch -c refactor/monorepo-flatten
```
Expected: `Switched to a new branch 'refactor/monorepo-flatten'`

- [ ] **Step 2: 워킹 트리가 깨끗한지 확인 (추적 파일 한정)**

Run:
```bash
git status --porcelain | grep -v '^??' || echo "CLEAN"
```
Expected: `CLEAN` (추적 파일에 미커밋 변경 없음). 변경이 있으면 먼저 커밋/스태시.

- [ ] **Step 3: baseline 테스트 실행 및 결과 저장**

Run:
```bash
python -m pytest -q 2>&1 | tail -20 | tee /tmp/baseline-pytest.txt
```
Expected: 통과/실패 요약이 출력됨. 마지막 줄(예: `123 passed`)을 기록해 둔다. 일부가 외부 의존(네트워크/DB)으로 실패하면 그 개수를 baseline으로 인정한다.

- [ ] **Step 4: shared 비-import 참조 사전 점검 (치환 안전성)**

Run:
```bash
grep -rn --include="*.py" -E "shared" . --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git \
  | grep -vE "(from shared|import shared)" \
  | grep -vE "#" || echo "NO_OTHER_SHARED_REFS"
```
Expected: `NO_OTHER_SHARED_REFS` 또는 주석/문자열뿐. 만약 `import shared_xxx` 같은 식별자 결합 참조가 보이면 Task 4의 치환식을 그 토큰을 피하도록 조정한다(아래 Task 4 Step 3 주석 참조).

---

### Task 1: backend 디렉토리 생성 + 코드/문서 이동 (git mv, 이름 유지)

**Files:**
- Create: `backend/` (디렉토리)
- Move: `app`, `scripts`, `config`, `fga`, `tests`, `docs`, `plan`, `reference`, `slides`, `conftest.py`, `pytest.ini`, `requirements.txt`, `docker-compose.yml`, `.env.example`, `CLAUDE.md` → `backend/`

- [ ] **Step 1: backend 디렉토리 생성**

Run:
```bash
cd /Users/acacian/vscode/company-rag
mkdir backend
```
Expected: 에러 없음.

- [ ] **Step 2: git 추적 디렉토리/파일을 git mv로 이동**

Run:
```bash
git mv app scripts config fga tests docs plan reference slides \
       conftest.py pytest.ini requirements.txt docker-compose.yml .env.example CLAUDE.md \
       backend/
```
Expected: 에러 없음. (이 시점에 `docs/`가 옮겨지므로 이 plan 파일도 `backend/docs/superpowers/plans/...`로 함께 이동한다 — 정상.)

- [ ] **Step 3: 이동 결과 확인**

Run:
```bash
ls backend/ && echo "--- 루트 잔여 ---" && ls
```
Expected: `backend/`에 app, scripts, config, fga, tests, docs, plan, reference, slides, conftest.py, pytest.ini, requirements.txt, docker-compose.yml, CLAUDE.md 존재. 루트엔 `backend`, `web`, `README.md`, `shared`(아직), `.git` 등.

- [ ] **Step 4: 커밋 (중간 체크포인트)**

Run:
```bash
git add -A && git commit -m "refactor: 백엔드 코드·문서를 backend/로 이동 (shared 제외)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: rename 다수 기록된 커밋 생성. `git show --stat HEAD | grep -c "=>"`로 rename 다건 확인.

---

### Task 2: shared/ → backend/core/ 리네임 (git mv)

**Files:**
- Move+Rename: `shared/` → `backend/core/`

- [ ] **Step 1: 리네임 이동**

Run:
```bash
cd /Users/acacian/vscode/company-rag
git mv shared backend/core
```
Expected: 에러 없음.

- [ ] **Step 2: 디렉토리 구조 확인**

Run:
```bash
ls backend/core/ | head && echo "--- 루트에 shared 없어야 ---" && ls | grep shared || echo "NO shared IN ROOT"
```
Expected: `backend/core/`에 chunker, embedder, fga, llm 등 기존 shared 하위가 보임. 루트에 `NO shared IN ROOT`.

- [ ] **Step 3: 커밋**

Run:
```bash
git add -A && git commit -m "refactor: shared/ → backend/core/ 디렉토리 리네임

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: rename 커밋 생성.

---

### Task 3: import 치환 (`shared` → `core`)

backend/ 전체의 파이썬 파일에서 `from shared` / `import shared`를 `from core` / `import core`로 바꾼다.

**Files:**
- Modify: `backend/` 하위 `*.py` 중 shared를 import하는 117개 파일

- [ ] **Step 1: 치환 대상 파일 수 확인 (치환 전)**

Run:
```bash
cd /Users/acacian/vscode/company-rag
grep -rl --include="*.py" -E "(from shared|import shared)" backend | wc -l
```
Expected: `117` (스펙 조사 시점 기준; 다르면 기록).

- [ ] **Step 2: 치환 실행 (macOS BSD sed)**

Run:
```bash
grep -rl --include="*.py" -E "(from shared|import shared)" backend \
  | xargs sed -i '' -E 's/^([[:space:]]*)from shared/\1from core/; s/^([[:space:]]*)import shared/\1import core/'
```
설명: 줄 시작(들여쓰기 허용) 뒤의 `from shared` / `import shared`만 치환한다. 변수·문자열 내 `shared`나 `import shared_xxx`(줄 시작이 아닌 위치는 영향 없음, 단 `import shared_xxx`는 줄 시작이므로 주의)를 피한다. Task 0 Step 4에서 `import shared_xxx` 류가 없음을 확인했다면 안전하다. 발견됐다면 치환식 뒤에 토큰 경계를 추가: `s/^([[:space:]]*)import shared([.[:space:]]|$)/\1import core\2/`.

- [ ] **Step 3: 잔존 shared import가 0건인지 검증**

Run:
```bash
grep -rn --include="*.py" -E "(from shared|import shared)" backend || echo "NO_REMAINING_SHARED_IMPORTS"
```
Expected: `NO_REMAINING_SHARED_IMPORTS`.

- [ ] **Step 4: core import가 생겼는지 확인 (스모크)**

Run:
```bash
grep -rln --include="*.py" -E "(from core|import core)" backend | wc -l
```
Expected: 약 117 (Step 1과 동일 수준).

- [ ] **Step 5: 커밋**

Run:
```bash
git add -A && git commit -m "refactor: shared → core import 경로 치환 (117 files)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: 다수 파일 변경 커밋.

---

### Task 4: git 미추적 런타임 파일 이동 (.env, .chroma, logs)

이들은 gitignore 대상이라 `git mv` 불가. 일반 `mv`로 옮긴다.

**Files:**
- Move: `.env`, `.chroma/`, `logs/` → `backend/`

- [ ] **Step 1: 존재하는 것만 이동**

Run:
```bash
cd /Users/acacian/vscode/company-rag
for p in .env .chroma logs; do
  if [ -e "$p" ]; then mv "$p" backend/ && echo "moved $p"; else echo "skip $p (없음)"; fi
done
```
Expected: 존재하는 항목은 `moved`, 없으면 `skip`.

- [ ] **Step 2: 결과 확인**

Run:
```bash
ls -a backend/ | grep -E "(\.env$|\.chroma|logs)" ; ls -a | grep -E "(\.env$|\.chroma|^logs$)" && echo "WARN: 루트에 잔존" || echo "루트 정리됨"
```
Expected: backend/에 이동된 항목 표시, 루트엔 `루트 정리됨`. (커밋 불필요 — 추적 대상 아님.)

---

### Task 5: .gitignore / README 경로 갱신

**Files:**
- Modify: `.gitignore` (루트)
- Modify: `README.md` (루트)

- [ ] **Step 1: 현재 .gitignore 확인**

Run:
```bash
cat /Users/acacian/vscode/company-rag/.gitignore
```
Expected 내용:
```
.env
.chroma/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

- [ ] **Step 2: .gitignore 경로를 신규 위치로 갱신**

`.gitignore`를 다음 내용으로 교체한다 (Edit/Write):
```
backend/.env
backend/.chroma/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
backend/logs/
web/dist/
.venv/
venv/
```
설명: `.env`·`.chroma`는 backend로 이동했으므로 경로 갱신. `logs/`도 backend로 이동했으니 명시. `dist/`는 web 빌드물이므로 `web/dist/`로 한정. `__pycache__/`·`*.pyc`·`.pytest_cache/`는 위치 무관 패턴이라 그대로.

- [ ] **Step 3: README의 디렉토리 트리 + 실행 안내 갱신**

`README.md`에서 디렉토리 트리를 신규 구조로 바꾸고, 백엔드 실행이 `cd backend` 전제임을 명시한다. 최소 다음을 반영:
- 트리: `backend/`(app, core, scripts, config, fga, tests, docs, plan, ...) 와 `web/`을 형제로.
- 기존 `web/` 줄을 backend 외부(형제)로 이동.
- `shared/` 표기를 `core/`로.
- 실행 예시에 `cd backend` 추가 (예: `cd backend && uvicorn app.api.main:app ...` 형태가 있으면 prefix).

먼저 README에서 갱신 지점을 찾는다:
```bash
grep -n -E "(web/|shared/|app/|\b(cd|uvicorn|pytest|python)\b)" /Users/acacian/vscode/company-rag/README.md | head -40
```
그 결과를 보고 트리/명령 블록을 신규 구조로 Edit한다.

- [ ] **Step 4: 커밋**

Run:
```bash
cd /Users/acacian/vscode/company-rag
git add .gitignore README.md && git commit -m "docs: .gitignore·README를 backend/web 수평 구조로 갱신

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: 2개 파일 변경 커밋.

---

### Task 6: backend 실행 루트에서 검증 (DoD)

이동·치환 후 baseline과 동일하게 동작하는지 확인한다.

**Files:** 없음 (검증)

- [ ] **Step 1: backend에서 import 스모크 테스트**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend
python -c "import app.api.chat; import core.config; print('IMPORT OK')"
```
Expected: `IMPORT OK`. ModuleNotFoundError가 나면 잔존 `shared` 참조 또는 sys.path 문제 → Task 3 재점검.

- [ ] **Step 2: 전체 테스트 (backend cwd)**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend
python -m pytest -q 2>&1 | tail -20
```
Expected: `/tmp/baseline-pytest.txt`의 통과 수와 **동일**. 차이가 있으면 원인(경로/import) 규명 후 수정.

- [ ] **Step 3: shared 잔존 0건 재확인 (전체 backend)**

Run:
```bash
cd /Users/acacian/vscode/company-rag
grep -rn --include="*.py" -E "(from shared|import shared)" backend || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 4: docker-compose 상대경로 유효성**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend
docker compose config >/dev/null 2>&1 && echo "COMPOSE OK" || echo "compose 점검 필요 (docker 미설치 시 무시)"
```
Expected: `COMPOSE OK` (docker 미설치면 무시).

- [ ] **Step 5: 이력 보존 확인**

Run:
```bash
cd /Users/acacian/vscode/company-rag
git log --follow --oneline backend/app/api/chat.py | head -3
git log --follow --oneline backend/core/config.py | head -3
```
Expected: 이동 이전 커밋 이력이 따라옴 (--follow로 rename 추적).

- [ ] **Step 6: 회귀 평가 (선택, eval 가능 시)**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend
python -m pytest tests/eval/runner.py -q 2>&1 | tail -10 || echo "eval 스킵 (외부 의존)"
```
Expected: baseline 대비 점수 하락 없음. 외부 의존으로 못 돌리면 스킵 사유 기록.

---

### Task 7: 최종 정리 + PR

**Files:** 없음

- [ ] **Step 1: 최종 트리 확인**

Run:
```bash
cd /Users/acacian/vscode/company-rag
find . -maxdepth 1 -not -name '.*' | sort
echo "--- backend top ---"
ls backend/
```
Expected: 루트 maxdepth1에 `backend`, `web`, `README.md`. backend엔 app, core, scripts, config, fga, tests, docs, plan, reference, slides 등.

- [ ] **Step 2: PR 생성 (사용자 확인 후)**

Run (사용자가 push/PR을 승인하면):
```bash
cd /Users/acacian/vscode/company-rag
git push -u origin refactor/monorepo-flatten
gh pr create --title "refactor: 모노레포 수평 구조 재편 (backend/web)" \
  --body "$(cat <<'EOF'
## 요약
루트=백엔드였던 구조를 `backend/`로 모아 `web/`과 형제 관계로 재편.

## 변경
- 백엔드 코드·문서 전부 `backend/`로 이동 (git mv, 이력 보존)
- `shared/` → `backend/core/` 리네임 + import 치환 (117 files)
- 런타임 파일(.env, .chroma, logs) backend로 이동
- .gitignore·README 경로 갱신

## DoD
- [x] backend에서 전체 테스트 baseline 동일 통과
- [x] `from shared`/`import shared` 잔존 0건
- [x] git --follow 이력 보존 확인

설계: `backend/docs/superpowers/specs/2026-05-29-monorepo-flatten-backend-web-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL 출력.

---

## 주의 / 비목표

- `.venv`는 이동하지 않는다. backend에서 재생성: `cd backend && python -m venv .venv && pip install -r requirements.txt`.
- `app`은 리네임하지 않는다 (실행 루트 변경으로 충분).
- `.idea/`는 재인덱싱 필요(코드 영향 없음).
- 모든 백엔드 명령은 `cd backend` 전제 — README에 명시.
