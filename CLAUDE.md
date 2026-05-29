# 프로젝트 안내 (Claude Code용) — 모노레포 루트

이 저장소는 백엔드와 프론트엔드가 **수평(형제) 관계**인 모노레포다.

```
company-rag/
├── backend/   # LangGraph 기반 RAG 챗봇 (Python 3.11+, FastAPI). 상세: backend/CLAUDE.md
├── web/       # Vite + React + TypeScript 프론트엔드. 상세: web/CLAUDE.md
└── README.md
```

## 작업 디렉토리 규칙 (중요)

- **백엔드 작업은 `backend/`를 작업 디렉토리로 실행한다.** 모든 경로(`config/users.yaml`, `logs/`, `.env`, `docker-compose.yml`)와 import(`app`, `core`)가 `backend/` cwd 기준이다.
  - venv는 **`backend/.venv/`**에 있다. backend cwd 기준 인터프리터는 `.venv/bin/python` (시스템에 `python` 없음).
  - 테스트: `cd backend && .venv/bin/python -m pytest`
- **프론트엔드 작업은 `web/`를 작업 디렉토리로 실행한다.** (`npm run dev` 등)
- 백엔드·프론트 양쪽을 건드리는 작업이면 루트에서 시작한다. 한 영역만 다루면 해당 하위 디렉토리에서 시작하면 그 영역의 CLAUDE.md만 로드되어 컨텍스트가 가볍다.

## 레이어 경계 (요약 — 상세는 `backend/CLAUDE.md`)

- `backend/core/`는 LangGraph를 모른다 (LangGraph 불가지 공용 인프라).
- `backend/app/`은 `core/`의 인터페이스(ABC)만 의존한다.
- `web/`는 백엔드 API(`VITE_API_BASE_URL`)로만 통신한다. 백엔드 코드를 직접 참조하지 않는다.

## 하위 지침

Claude Code는 작업하는 디렉토리의 CLAUDE.md를 자동 로드한다. 영역별 규약은 각 하위 파일을 따른다.
- 백엔드 규약·아키텍처 결정·작업 규칙 → `backend/CLAUDE.md`
- 프론트엔드 스택·실행·테스트 규약 → `web/CLAUDE.md`
- LangGraph 설계/구현 → `backend/docs/langgraph-guide/INDEX.md`
- ADR → `backend/docs/superpowers/decisions/`
