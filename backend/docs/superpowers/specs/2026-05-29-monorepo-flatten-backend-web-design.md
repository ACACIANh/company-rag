# 모노레포 수평 구조 재편 — backend / web 분리

- 날짜: 2026-05-29
- 상태: 설계 승인 대기
- 작성: 브레인스토밍 세션

## 1. 배경 / 문제

현재 레포 **루트가 곧 백엔드**다. `app/`, `shared/`, `scripts/`, `config/`, `fga/`, `tests/`,
`conftest.py`, `pytest.ini`, `requirements.txt`, `docker-compose.yml`, `.env` 등 백엔드 코드·설정이
모두 루트에 흩어져 있고, 프론트엔드 `web/`(Vite)는 그 **하위**에 들어가 있다.

이 구조는 "백엔드가 프론트를 품고 있는" 비대칭이다. 백엔드와 프론트엔드를 **형제(수평) 관계**로
재편해 모노레포 성격을 명확히 한다.

### 현재 결합도 (조사 결과)

- 백엔드 파이썬 코드는 `web/` 경로를 **참조하지 않는다**. vite proxy 설정도 없다 → 두 영역은
  코드 레벨에서 거의 독립적이다.
- 백엔드의 모든 경로 의존은 **cwd(실행 디렉토리) 기준 상대경로**다:
  - `Path("config/users.yaml")` — `app/api/auth.py`, `app/api/admin.py`, `scripts/seed_fga.py`
  - `Path("logs")` / `"logs"` — `app/api/chat.py`, `app/api/admin.py`,
    `shared/observability/sinks/file_sink.py`, `scripts/cost_report.py`
  - `load_dotenv()` (인자 없음) — `shared/config.py`
  - `sys.path.insert(0, os.path.dirname(__file__))` — `conftest.py`
  - `./fga/pg-init` — `docker-compose.yml`
- `shared` import 참조: **117개 파일, 271개 라인** (절대 import `from shared...` / `import shared`).
  `shared/` 내부 파일들도 서로를 `from shared.xxx`로 참조한다.
- `app` import 참조: 98개 라인.

## 2. 목표 구조

```
company-rag/
├── backend/                  # 자족적 백엔드 (실행 루트 = 이 디렉토리)
│   ├── app/                  # LangGraph 워크플로우 + FastAPI
│   ├── core/                 # 기존 shared/ — LangGraph 모르는 공용 인프라
│   ├── scripts/
│   ├── config/               # users.yaml
│   ├── fga/                  # model.json, model.fga, pg-init/
│   ├── tests/
│   ├── docs/                 # langgraph-guide, superpowers(ADR/specs), company
│   ├── plan/
│   ├── reference/
│   ├── slides/
│   ├── logs/                 # 런타임 로그 (gitignore)
│   ├── .chroma/              # 레거시 런타임 데이터 (gitignore)
│   ├── conftest.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── .env  .env.example
│   └── CLAUDE.md             # 내부 상대경로(docs/, app/) 그대로 유효
├── web/                      # Vite 프론트엔드 (변경 없음)
├── README.md                 # 모노레포 전체 소개 (디렉토리 트리 갱신)
├── .gitignore                # 경로 갱신
├── .git/  .claude/  .idea/  .superpowers/  trash/   # 루트 유지
```

### 핵심 결정

1. **백엔드 폴더명 = `backend`**, 프론트 = `web` → 형제 관계.
2. **`shared/` → `core/` 리네임**. 117개 파일에서 `from shared` → `from core`,
   `import shared` → `import core` 치환.
3. **`app/`은 이름 유지**. `backend/`가 실행 루트가 되면 `from app...`은 그대로 동작 → import 변경 불필요.
4. **자족적 backend**: `CLAUDE.md`·`docs`·`plan` 등 백엔드 거버넌스 문서까지 모두 `backend/`로.
   `CLAUDE.md` 내부의 `docs/...`, `app/...`, ADR 경로 `docs/superpowers/decisions/`가 상대경로
   그대로 유효해진다 (함께 이동하므로 깨지지 않음).
5. **`git mv`로 이동** → 파일 이력(blame/log) 보존. 단 git 미추적 파일(`.env`)은 일반 `mv`.

### 루트 유지 항목과 근거

- `.git/` — 레포 루트 필수.
- `.claude/` — Claude Code가 cwd 상위에서 탐색하는 설정. 루트 유지.
- `.idea/`, `.superpowers/` — IDE / 도구 상태.
- `README.md` — 모노레포 진입점. 디렉토리 트리 설명을 신규 구조로 갱신.
- `.gitignore` — 루트 유지하되 경로 갱신(아래).
- `trash/` — git 추적되는 잡동사니. 백엔드 코드 아님 → 루트 유지.

## 3. 실행에 영향이 "없는" 이유 (검증 포인트)

모든 백엔드 경로가 cwd 상대경로이므로, **실행·테스트를 `backend/`에서 수행**하면 경로가 그대로 맞는다:

| 의존 | 현재 (cwd=루트) | 이후 (cwd=backend) | 코드 수정 |
|---|---|---|---|
| `config/users.yaml` | `<root>/config/...` | `backend/config/...` | 불필요 |
| `logs/` | `<root>/logs` | `backend/logs` | 불필요 |
| `load_dotenv()` | `<root>/.env` | `backend/.env` | 불필요 |
| `conftest.py` sys.path | 루트를 path에 | backend를 path에 → `app`,`core` import | 불필요 |
| `docker-compose ./fga/pg-init` | `<root>/fga/...` | `backend/fga/...` | 불필요 |

→ **유일한 코드 변경은 `shared`→`core` 리네임에 따른 import 치환.**

## 4. 변경 분류

### A. `git mv`로 backend/로 이동 (이름 유지)
`app`, `scripts`, `config`, `fga`, `tests`, `docs`, `plan`, `reference`, `slides`,
`conftest.py`, `pytest.ini`, `requirements.txt`, `docker-compose.yml`, `.env.example`, `CLAUDE.md`

### B. `git mv` + 리네임
`shared/` → `backend/core/`

### C. 일반 `mv` (git 미추적)
`.env`, `.chroma/`, `logs/`

### D. import 치환 (이동 후, backend/ 전체 대상)
- `from shared` → `from core`
- `import shared` → `import core`
- 검증: 치환 후 `grep -rn "shared" backend --include=*.py`로 잔존 `shared` 참조 0건 확인
  (단, 변수명·주석의 "shared"는 오검출 가능 → import 라인 한정 치환).

### E. 경로 문자열 갱신
- `.gitignore`: `.chroma/` → `backend/.chroma/`, `dist/` → `web/dist/` 등 신규 위치 반영.
- `README.md`: 디렉토리 트리 + 실행 명령(`cd backend`) 갱신.
- `CLAUDE.md`: 내부 경로는 함께 이동하므로 **수정 불필요**. (검증만)

### F. 손대지 않음
`web/` 전체, `.git/`, `.claude/`, `.idea/`, `.superpowers/`, `trash/`,
재생성 가능한 캐시(`__pycache__`, `.pytest_cache`, `.ruff_cache`), `.venv`(아래).

### `.venv` 처리
`.venv`는 gitignore되고 활성 경로가 깨질 수 있다. **이동하지 않고 backend/에서 재생성** 권장
(`cd backend && python -m venv .venv && pip install -r requirements.txt`). 설계상 backend 소속이나
물리 이동은 리스크가 크므로 재생성으로 갈음.

## 5. 검증 (DoD)

1. `cd backend && python -m pytest` — 전체 테스트 통과 (이동 전 baseline과 동일).
2. `grep -rn -E "(from shared|import shared)" backend --include=*.py` → **0건**.
3. `cd backend && python -m pytest tests/eval/runner.py` 또는 회귀 스코어 — 이동 전과 동일.
4. `docker compose -f backend/docker-compose.yml config` — 상대경로 유효성 확인.
5. `git log --follow backend/app/api/chat.py` 등으로 이력 보존 확인.

## 6. 비목표 (YAGNI)

- `app`을 `backend`로 별도 리네임하지 않음 (실행 루트 변경으로 충분).
- `backend`/`core`를 최상위 형제로 분리하지 않음 (단일 파이썬 루트 유지가 단순).
- web–backend 통합 서빙(FastAPI가 vite 빌드물 서빙)은 범위 밖.
- 모노레포 워크스페이스 도구(turborepo, pnpm workspace 등) 도입 안 함.

## 7. 리스크

- **import 치환 오검출**: `shared`가 변수/문자열로도 등장할 수 있음 → import 라인 한정 치환 + grep 검증.
- **IDE 인덱스**: `.idea/`가 옛 경로를 캐시 → 재인덱싱 필요(코드 영향 없음).
- **실행 습관 변경**: 모든 백엔드 명령이 `cd backend` 전제 → README에 명시.
