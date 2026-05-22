# 내부 API 명세

## 기본 규칙
- Base URL: https://api.acmecorp.com/v1
- 인증: Bearer 토큰 (Authorization 헤더)
- 응답 형식: JSON
- 날짜 형식: ISO 8601 (UTC)

## 공통 응답 형식
```json
{
  "success": true,
  "data": {},
  "error": null,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

## 주요 엔드포인트

### 사용자 API
- GET /users/{id} — 사용자 정보 조회
- POST /users — 사용자 생성
- PATCH /users/{id} — 사용자 정보 수정
- DELETE /users/{id} — 사용자 비활성화 (소프트 삭제)

### 프로젝트 API
- GET /projects — 프로젝트 목록 (페이지네이션: ?page=1&size=20)
- POST /projects — 프로젝트 생성
- GET /projects/{id}/members — 프로젝트 멤버 목록

## 에러 코드
- 400: 잘못된 요청 (request body 검증 실패)
- 401: 인증 실패 (토큰 만료 또는 없음)
- 403: 권한 없음
- 404: 리소스 없음
- 429: 요청 한도 초과 (분당 100건)
- 500: 서버 내부 오류
