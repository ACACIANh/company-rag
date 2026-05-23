# Phase 5: 운영 준비 설계 스펙

**Date**: 2026-05-23  
**Approach**: Option A — 보안 우선 (인증 → ACL → Rate Limiting/비용 모니터링 → 어드민 API → 부하 테스트)

---

## 1. 인증 (Mock/JWT)

### 구조

```
shared/auth/
├── base.py          # AuthUser TypedDict (user_id, roles, allowed_doc_ids)
└── jwt_handler.py   # encode / decode / 만료 검증

app/api/
├── auth.py          # POST /auth/token, GET /auth/me
└── deps.py          # get_current_user() — FastAPI Depends
```

### 흐름

1. `POST /auth/token` — `{username, password}` → Mock 사용자 테이블 조회 → JWT 반환
2. 모든 보호 엔드포인트 `Depends(get_current_user)` → `AuthUser` 주입
3. `AuthUser`: `user_id: str`, `roles: list[str]`, `allowed_doc_ids: list[str]`

### Mock 사용자 테이블

`config/users.yaml`에 테스트 계정 하드코딩. 실제 SSO 연동 시 `jwt_handler` 교체만으로 전환 가능하도록 인터페이스 분리.

### 레이어 경계

`shared/auth/`는 FastAPI를 모름. `app/api/deps.py`가 `shared/auth/`를 호출해 `AuthUser` 반환. 기존 레이어 규칙 유지.

---

## 2. 권한 기반 문서 필터링 (ACL)

### AgentState 확장

```python
class AgentState(TypedDict):
    ...기존 필드...
    user_id: str
    allowed_doc_ids: list[str]   # 빈 리스트 = 전체 허용
```

### 검색 필터링

`retrieve_node`에서 벡터 쿼리 시 `allowed_doc_ids`를 `where` 필터로 강제 주입.

```
shared/vector_store/base.py        # search() 시그니처에 filter_doc_ids 파라미터 추가
shared/vector_store/chroma_store.py  # where={"doc_id": {"$in": allowed_doc_ids}}
shared/vector_store/qdrant_store.py  # must 조건으로 doc_id filter 적용
```

### AuthUser → AgentState 주입 경로

`app/api/chat.py`의 `/chat` 핸들러가 `Depends(get_current_user)`로 `AuthUser`를 받아 그래프 초기 State에 주입:

```python
initial_state = {
    "question": request.question,
    "user_id": current_user["user_id"],
    "allowed_doc_ids": current_user["allowed_doc_ids"],
    ...
}
graph.invoke(initial_state, config={"configurable": {"thread_id": session_id}})
```

### 핵심 불변식

- `allowed_doc_ids`가 비어 있지 않으면 반드시 필터 적용. 누락 = 버그
- `web_search_node`는 사내 문서 외부이므로 필터 대상 아님
- 인덱싱 시 각 청크에 `doc_id` 필드 필수 포함 (`app/ingestion/indexer.py` 수정)

---

## 3. Rate Limiting + 비용 모니터링

### Rate Limiting

```
shared/rate_limiter/
├── base.py              # RateLimiter ABC — is_allowed(user_id, endpoint) -> bool
├── in_memory.py         # 슬라이딩 윈도우 dict (개발/소규모)
└── redis_limiter.py     # Redis 기반 (운영, 나중에 추가)
```

- `app/api/deps.py`에 `check_rate_limit` Depends 체이닝
- 기본값: 사용자당 분당 20회 (`config.py`에서 조정)
- `config.py`에 `RATE_LIMIT_RULES: dict[str, int]` — role별/endpoint별 limit 외부 설정
- 초과 시 HTTP 429 + `Retry-After` 헤더

### 비용 모니터링 (Sink 패턴)

```
shared/observability/
├── cost_tracker.py      # 토큰 집계, Sink 목록으로 fan-out
└── sinks/
    ├── base.py          # CostSink ABC — record(user_id, tokens, cost, model)
    ├── file_sink.py     # logs/cost_YYYY-MM-DD.jsonl (기본)
    ├── prometheus_sink.py  # /metrics 엔드포인트 (선택)
    └── langsmith_sink.py   # LangSmith custom metadata (선택)
```

```python
class CostTracker:
    def __init__(self, sinks: list[CostSink]):
        self.sinks = sinks

    def track(self, user_id, tokens, model):
        cost = self._calculate(tokens, model)
        for sink in self.sinks:
            sink.record(user_id, tokens, cost, model)
```

- `generate_node` 호출 후 `cost_tracker.track()` 실행
- 초기: `[FileSink]`만 주입. Prometheus/DataDog 추가 시 Sink만 구현

---

## 4. 어드민 API

### 구조

```
app/api/
└── admin.py    # /admin/* 라우터
```

### 엔드포인트

| 엔드포인트 | 메서드 | 기능 |
|---|---|---|
| `/admin/index/status` | GET | 인덱스 상태 (총 청크 수, 마지막 인덱싱 시각) |
| `/admin/index/rebuild` | POST | 문서 재인덱싱 트리거 (202 즉시 반환, 백그라운드 실행) |
| `/admin/eval/run` | POST | 평가셋 실행 → recall@5 등 결과 반환 |
| `/admin/eval/results` | GET | 최근 평가 결과 목록 |
| `/admin/cost/report` | GET | 일별 비용 집계 (`?date=YYYY-MM-DD`) |
| `/admin/users` | GET | Mock 사용자 목록 + 권한 조회 |
| `/admin/users/{user_id}/docs` | PUT | 사용자 `allowed_doc_ids` 갱신 |

### 권한 미들웨어

```python
def require_admin(user: AuthUser = Depends(get_current_user)):
    if "admin" not in user["roles"]:
        raise HTTPException(403)
    return user
```

### 설계 원칙

- 어드민 API는 비즈니스 로직 없음. 기존 모듈(`app/ingestion/`, `shared/observability/`)을 호출하는 얇은 레이어
- 재인덱싱은 `FastAPI BackgroundTasks`로 실행

---

## 5. 부하 테스트 (Locust)

### 구조

```
tests/load/
├── locustfile.py       # 시나리오 정의
└── config.py           # 환경별 설정
```

### 시나리오

| 태스크 | 비중 | 내용 |
|---|---|---|
| `chat_doc_search` | 70% | `/chat` — 사내 문서 Q&A |
| `chat_web_search` | 20% | `/chat` — 웹 검색 경로 |
| `admin_cost_report` | 10% | `/admin/cost/report` |

### 실행

```bash
# 웹 UI
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Headless (CI)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless
```

### DoD 기준

- 동시 사용자 50명, 60초 지속
- P95 응답시간 < 10초, 에러율 < 1%
- CI: `MOCK_LLM=true`로 LLM Mock 처리해 비용 없이 인프라 테스트

---

## DoD 체크리스트

- [ ] 동시 50명 부하 테스트 통과 (P95 < 10s, 에러율 < 1%)
- [ ] 비인가 문서 노출 0건 (ACL 필터 단위 테스트)
- [ ] 일일 비용 리포트 자동화 (`/admin/cost/report` + FileSink)
- [ ] JWT 인증 단위 테스트
- [ ] Rate limiting 단위 테스트 (429 응답 확인)
- [ ] 어드민 role 검증 테스트 (403 응답 확인)
- [ ] 회귀 테스트 통과 (Phase 4 recall@5 ≥ 0.80 유지)
