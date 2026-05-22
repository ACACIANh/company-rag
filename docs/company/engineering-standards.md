# 엔지니어링 표준

## 언어 및 프레임워크
- 백엔드: Kotlin + Spring Boot (신규), Python (AI/데이터)
- 프론트엔드: TypeScript + React + Next.js
- 인프라: Terraform + AWS + Kubernetes

## 코딩 컨벤션
- 모든 언어: Prettier/ktlint/black 자동 포매팅 (PR에서 자동 검사)
- 커밋 메시지: Conventional Commits (feat, fix, refactor, chore, docs, test)
- 브랜치 전략: GitHub Flow (feature/이슈번호-설명)

## 테스트 기준
- 신규 코드: 라인 커버리지 80% 이상
- 통합 테스트: 핵심 API 엔드포인트 100% 커버
- E2E: 핵심 사용자 시나리오 3개 이상

## 문서화
- 공개 API: OpenAPI 3.0 명세 필수
- 아키텍처 결정: ADR(Architecture Decision Record) 작성
- 복잡한 비즈니스 로직: 인라인 주석 + README

## 보안 기준
- 의존성 취약점: Dependabot 알림 7일 이내 해결
- OWASP Top 10 기준 준수
- 비밀값은 AWS Secrets Manager 또는 환경변수로만 관리
