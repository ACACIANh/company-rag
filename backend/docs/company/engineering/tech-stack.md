# 기술 스택

## 개요
회사 제품에서 사용하는 기술 스택을 정리한다. 새 기술 도입은 엔지니어링 표준에 따라 RFC를 거친다.

## 언어
- 백엔드: Python (FastAPI), 일부 서비스는 Kotlin/Spring
- 프론트엔드: TypeScript

## 프레임워크 / 라이브러리
- 백엔드: FastAPI, Pydantic, SQLAlchemy
- 프론트엔드: React, Vite, TanStack Query
- AI/검색: LangGraph, LangChain

## 데이터베이스
- 주 데이터베이스: PostgreSQL
- 캐시: Redis
- 벡터 검색: pgvector

## 인프라
- 컨테이너: Docker
- 오케스트레이션: Kubernetes
- CI/CD: GitHub Actions
- 클라우드: AWS

## 관측성
- 로그: 구조화 JSON 로그
- 메트릭: Prometheus
- 대시보드: Grafana

## 기술 선택 원칙
- 검증된 스택을 우선한다.
- 팀 내 운영 경험이 있는 도구를 선호한다.
- 새 스택 도입 시 마이그레이션 비용과 학습 곡선을 함께 검토한다.
