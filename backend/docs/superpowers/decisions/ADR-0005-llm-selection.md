# ADR-0005: RAG LLM 선택

> **Status**: 🟢 적용완료

**Date**: 2026-05-23
**Context**: 접근 권한 제어 파이프라인에서 사용할 LLM 결정

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| Claude (Anthropic) | 현재 스택(langchain-anthropic)과 일치, 긴 컨텍스트 창 |
| OpenAI | 생태계 넓음, 별도 API 키 관리 필요 |
| Ollama (로컬) | 외부 유출 없음, GPU 리소스 필요, 품질 편차 |

## Decision

**선택: 현재 구현 유지 (Claude, langchain-anthropic)**

## Rationale

이미 `Retriever` ABC 추상화로 LLM 교체가 가능한 구조이므로, 현재 동작하는 구현을 변경할 이유가 없다. 접근 권한 제어 기능은 LLM 종류와 무관하게 Pre-filter 레이어에서 동작한다. 필요 시 환경 변수 교체만으로 전환 가능.
