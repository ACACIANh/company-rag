# Backlog

카테고리 태그: `#perf` `#dx` `#feat` `#refactor` `#test` `#infra` `#doc`

---

## High

- `#infra` 배포를 위한 컨테이너화 — Dockerfile(app/worker 분리) + docker-compose(app, qdrant, redis) 작성, `.env` 주입 방식 정의
- `#perf` Reranker 연결 (C-10) — `shared/reranker/` 폴더 존재, `retrieve_node` 이후 rerank 단계 삽입하여 검색 품질 개선
- `#perf` Hybrid Search (C-9) — 현재 Vector Only, BM25 결합으로 recall 향상 / Qdrant sparse vector 또는 별도 BM25 인덱스 검토
- `#infra` 비밀번호 해싱 (A-6) — 현재 `config/users.yaml` 평문 저장, bcrypt 해싱으로 전환

<!-- 빠르게 처리해야 하는 개선사항 -->

## Medium

- `#feat` 스트리밍 응답 (B-6) — `POST /chat` SSE 또는 WebSocket 스트리밍, 프론트 연동 포함
- `#feat` 첫 질문창 진입 시 추천 질문 3개 제안 (빈 채팅 화면에 샘플 질문 버튼 표시)
- `#feat` 문서 접근 제어 개선 (A-5) — 현재 `allowed_doc_ids: []`이면 전체 허용. role 기반(admin=전체, user=지정 문서)으로 전환 검토

<!-- 다음 Phase 계획 시 고려할 항목 -->

## Low

- `#feat` 관리자 UI (F-6) — `/admin` REST API 완비, 관리자 전용 SPA 또는 대시보드 페이지 추가

<!-- 언젠가 하면 좋을 것들 -->

---

> 작업 시작 시 GitHub Issue로 옮기고 여기서 삭제.
