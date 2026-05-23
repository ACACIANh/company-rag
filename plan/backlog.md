# Backlog

카테고리 태그: `#perf` `#dx` `#feat` `#refactor` `#test` `#infra` `#doc`

---

## High

- `#infra` **접근 권한 제어 (OpenFGA + Chroma Pre-filter)** — ABAC/RBAC 혼합 모델 구현. 상세 설계: [`plan/access-control.md`](access-control.md), 결정 사항: [`docs/superpowers/decisions/2026-05-23-openfga-hosting.md`](../docs/superpowers/decisions/2026-05-23-openfga-hosting.md) 외 3개 ADR
- `#perf` Hybrid Search (C-9) — 현재 Vector Only, BM25 결합으로 recall 향상 / Qdrant sparse vector 또는 별도 BM25 인덱스 검토

<!-- 빠르게 처리해야 하는 개선사항 -->

## Medium

- `#infra` 배포를 위한 컨테이너화 — Dockerfile(app/worker 분리) + docker-compose(app, qdrant, redis) 작성, `.env` 주입 방식 정의. _현재 개발 단계에서는 venv로 충분; FastAPI 외부 배포 또는 벡터 DB 로컬 구동 시점에 착수_
- `#feat` 스트리밍 응답 (B-6) — `POST /chat` SSE 또는 WebSocket 스트리밍, 프론트 연동 포함
- `#feat` 대화 세션 목록 사이드바 — 좌측 세션 리스트(신규/이전 대화 전환), `GET /sessions` 엔드포인트 + 세션 제목 자동 생성(첫 질문 앞 20자), 세션 히스토리 DB 영속화(로그아웃 후 재로그인 시 복원), 프론트 상태 관리 포함
- `#feat` 열람 가능 문서 목록 표시 — `GET /docs` 엔드포인트(JWT 기반 필터링) + 프론트 사이드바/첫 화면 칩 표시
- `#feat` 첫 질문창 진입 시 추천 질문 3개 제안 (빈 채팅 화면에 샘플 질문 버튼 표시)

<!-- 다음 Phase 계획 시 고려할 항목 -->

<!-- 언젠가 하면 좋을 것들 -->

---

> 작업 시작 시 GitHub Issue로 옮기고 여기서 삭제.
