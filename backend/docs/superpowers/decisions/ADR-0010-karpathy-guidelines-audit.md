# ADR-0010: Karpathy Guidelines 적용 감사 보고서

**Date**: 2026-05-26  
**Source**: https://github.com/multica-ai/andrej-karpathy-skills  
**대상**: `/Users/acacian/vscode/company-rag` (company-rag 프로젝트 CLAUDE.md)

---

## 개요

Andrej Karpathy가 제시한 LLM 코딩 실수 방지 4원칙과 현재 프로젝트의 `CLAUDE.md`를 비교해 일치/불일치를 정리한 감사 보고서입니다.

---

## Karpathy 4원칙 요약

| # | 원칙 | 핵심 내용 |
|---|------|---------|
| 1 | **Think Before Coding** | 가정을 명시하고, 혼란을 숨기지 말고, 트레이드오프를 드러낼 것 |
| 2 | **Simplicity First** | 요청한 것만 구현. 추측성 기능·추상화·에러 핸들링 금지 |
| 3 | **Surgical Changes** | 요청에 해당하는 줄만 수정. 기존 스타일 유지. 사이드이펙트 금지 |
| 4 | **Goal-Driven Execution** | 작업을 검증 가능한 목표로 전환. 계획 → 검증 루프 |

---

## 원칙별 비교 분석

### 1. Think Before Coding — **부분 일치** ⚠️

**일치하는 부분:**
- `AskUserQuestion` 툴: 설계·방향·도구 선택 시 반드시 사용 → 명시적 가정 공개
- 결정 기록 규칙(ADR): 설계 선택 시 즉시 결정 파일 생성 → 트레이드오프 문서화

**미반영된 부분:**
- Karpathy 원칙은 **모든 코딩 상황**에서 가정을 명시하고 질문하도록 요구함
- 현재 CLAUDE.md는 "설계·방향·도구 선택"에만 `AskUserQuestion`을 적용하고, 일반적인 코드 구현 시의 혼란 처리 규칙이 없음
- 예: 새 노드를 추가할 때 함수 시그니처·파라미터 해석이 모호해도 별도 지침 없음

**리스크:** Claude가 코드 구현 중 잘못된 가정을 조용히 선택하고 진행할 수 있음

---

### 2. Simplicity First — **의도적 차이** ℹ️

**프로젝트에 있는 부분:**
- 작업 규칙: "외부 API 호출 노드: 반드시 retry + timeout 설정" — 목적이 명확한 복잡성
- 레이어 경계: ABC + Factory 패턴 — 교체 가능성을 위한 명시적 설계

**의도적으로 다른 부분:**
- 메모리 기록(`feedback_prefers_abstraction.md`): **미연결 추상화라도 삭제 권하지 말 것 — 학습 목적 + 구현체 교체 가능성**
- 이는 Karpathy의 "No abstractions for single-use code"와 **정면 충돌**
- `shared/orchestrator/` (pipeline.py, step.py, context.py), `shared/reranker/noop_reranker.py` 등이 이 철학의 산물

**판단:** 의도적 결정이므로 문제가 아님. 단, CLAUDE.md에 이 결정의 이유가 명시되지 않아 Claude가 추후 "단순성을 위해 삭제"할 리스크가 있음.

**권고:** CLAUDE.md 작업 규칙에 추상화 유지 정책을 명시 추가

---

### 3. Surgical Changes — **원칙 미반영** ❌

**현재 CLAUDE.md에 없는 내용:**
- 요청에 직접 연관된 줄만 수정하라는 규칙 없음
- 기존 스타일을 맞추라는 규칙 없음 (레이어 경계 규칙은 있지만 스타일 언급 없음)
- 인접 코드·주석·포맷을 건드리지 말라는 규칙 없음

**실제 리스크:**
```
사용자: "retrieve 노드에 로깅 추가해줘"
Claude가 할 수 있는 것:
  - 함수 시그니처에 type hint 추가
  - 인접한 주석 개선
  - 관련 없는 import 정리
  - 포맷 변경
```

**Karpathy CLAUDE.md에는 명시된 규칙:**
```
"Don't 'improve' adjacent code, comments, or formatting."
"Match existing style, even if you'd do it differently."
"The test: Every changed line should trace directly to the user's request."
```

**권고:** 현재 CLAUDE.md에 Surgical Changes 섹션 추가 필요 (가장 큰 격차)

---

### 4. Goal-Driven Execution — **부분 일치** ⚠️

**일치하는 부분:**
- DoD(Definition of Done): "단위 테스트 추가 → 회귀 점수 확인 → ADR 갱신" — 완료 시점 검증
- Phase 작업 워크플로우: PR DoD 체크리스트 → 검증 후 머지

**미반영된 부분:**
- Karpathy 원칙은 **작업 시작 전** 성공 기준을 정의하도록 요구함
- 현재 DoD는 **완료 시점**에 체크하는 형태 (사후 검증)
- 멀티스텝 작업 시 명시적인 "계획 → 검증" 루프 구조 없음

**예시 (Karpathy 방식):**
```
사용자: "grade_documents 노드에 신뢰도 점수 추가해줘"
이상적:
  1. grade_documents의 현재 반환값 확인 → verify: 테스트로 기존 동작 확인
  2. relevance_score 필드 추가 → verify: 테스트 통과
  3. 회귀 확인 → verify: eval runner recall@5 동일
```

**권고:** 작업 규칙에 "작업 시작 전 성공 기준(검증 방법) 명시" 추가

---

## 현재 CLAUDE.md에만 있는 사항 (Karpathy 원칙 대비 추가분)

이 항목들은 Karpathy 원칙에 없지만 프로젝트에 필수적으로 잘 설계된 부분입니다.

| 항목 | 내용 | 평가 |
|------|------|------|
| Phase 워크플로우 | 브랜치 → PR(DoD 체크리스트) → 태그 | ✅ 탁월한 구조 |
| 레이어 경계 | shared/는 LangGraph 모름, app/는 ABC만 의존 | ✅ 핵심 아키텍처 가드레일 |
| ADR 규칙 | 설계 선택 즉시 문서화 | ✅ 이상적인 의사결정 추적 |
| LangGraph 패턴 참조 | docs/langgraph-guide/ 먼저 읽기 | ✅ 지식 기반 작업 유도 |
| FGA 2-tier Pre-filter | 구체적 구현 패턴 명시 | ✅ 도메인 특화 가이드 |

---

## 격차 요약표

| Karpathy 원칙 | 현재 CLAUDE.md | 상태 | 심각도 |
|--------------|---------------|------|--------|
| Think Before Coding | AskUserQuestion (설계 결정 시만) | 부분 일치 | 중간 |
| Simplicity First | 의도적으로 추상화 선호 (메모리 기록) | 의도적 차이 | 낮음 (단, 문서화 필요) |
| Surgical Changes | **규칙 없음** | **미반영** | **높음** |
| Goal-Driven Execution | DoD 존재 (사후 검증만) | 부분 일치 | 중간 |

---

## 권고 사항 (우선순위 순)

### P1 — 즉시 반영 권장

**Surgical Changes 섹션 추가** (`CLAUDE.md` 작업 규칙에):
```markdown
## 수술적 변경 원칙
- 요청에 해당하는 코드만 수정. 인접 코드·주석·포맷 수정 금지.
- 기존 스타일(따옴표, 타입힌트 유무, 공백)을 그대로 유지.
- 내가 만든 변경이 발생시킨 dead code(import, 함수)만 정리.
- 기존 dead code는 발견해도 언급만 하고 삭제하지 않는다.
```

### P2 — 단기 반영 권장

**추상화 유지 정책 명시** (작업 규칙에):
```markdown
- shared/의 ABC 및 미연결 구현체는 학습 목적과 구현체 교체 가능성을 위해 유지.
  삭제를 제안하거나 실행하지 않는다.
```

**작업 시작 전 목표 정의 추가** (DoD 앞에):
```markdown
## 작업 시작 전 체크
멀티스텝 작업은 착수 전 다음을 명시:
1. 성공 기준 (무엇이 달라져야 하는가)
2. 검증 방법 (어떤 테스트로 확인하는가)
3. 회귀 방지 (eval runner 점수 비교)
```

### P3 — 선택적 반영

**Think Before Coding 일반화**: 현재는 설계 결정에만 적용되는 "명시적 가정 공개" 원칙을 일반 코딩에도 확장. 단, 너무 자주 질문하면 개발 속도가 저하될 수 있으므로 "30분 이상 소요될 비자명한 구현"에만 제한 적용하는 절충안도 가능.

---

## 결론

현재 프로젝트 CLAUDE.md는 Karpathy 4원칙 중 **일부를 도메인에 맞게 잘 반영**하고 있지만, **Surgical Changes 원칙이 완전히 누락**되어 있는 것이 가장 큰 격차입니다. 추상화 선호 정책은 의도적 결정이지만 CLAUDE.md에 명시되어 있지 않아 미래 세션에서 충돌이 발생할 수 있습니다.

전체적으로 Phase 워크플로우, 레이어 경계, ADR 규칙은 Karpathy 원칙을 넘어서는 프로젝트 특화 우수 사례로 평가됩니다.
