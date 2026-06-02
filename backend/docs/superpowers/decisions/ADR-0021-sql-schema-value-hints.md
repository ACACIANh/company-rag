# ADR-0021: NL→SQL 생성 — 카테고리형 컬럼 값 힌트(value hints)

> **Status**: ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-02
**Context**: `sql_generate_node`([app/graph/nodes/sql_generate.py](../../../app/graph/nodes/sql_generate.py))의 `SQL_GENERATE_PROMPT`([app/graph/prompts.py](../../../app/graph/prompts.py))는 테이블·컬럼·타입(스키마)만 LLM에 주고 **실제 컬럼 값의 형태**는 주지 않는다. 그 결과 사용자가 "엔지니어링 부서"라 물으면 DB가 영문(`engineering`)으로 저장된 `department`에 `WHERE department = '엔지니어링'`처럼 빗나간 리터럴을 생성해 조회가 비는 **value mismatch** 버그가 발생했다. 자연어→SQL의 정석 처방인 *value hints*(카테고리형 컬럼의 허용값을 프롬프트에 주입)를 도입할지, 그리고 그 출처와 PII 경계를 어떻게 둘지 결정한다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| 정적 하드코딩 | 프롬프트 문자열에 허용값을 직접 박음. 가장 단순·토큰 적음. 그러나 시드 값이 늘면 프롬프트를 손수 갱신해야 하고, 누락 시 동일 버그 재발(drift) |
| **공유 카탈로그 참조** | 카테고리형 허용값을 한 곳(`core/sql/catalog.py`)에 선언하고 시드·프롬프트가 함께 소비. drift 원천 차단, PII 컬럼 일괄 통제. 소규모 리팩터링 비용 |
| 동적 distinct-value 조회 | 런타임 `SELECT DISTINCT` + 캐시로 항상 최신. 그러나 결정론적 소규모 시드 DB에선 최신성 실익이 없고, 추가 쿼리·캐시·고카디널리티/PII allowlist 강제 등 복잡도만 늘어남 |
| few-shot 예시(질문→SQL 쌍) | 스키마/조인 오해(다른 실패 모드)엔 효과적이나, 이번 value mismatch는 못 잡음. 직교적 후속 과제 |

## Decision

**선택: 카테고리형 컬럼의 허용값을 단일 카탈로그에서 끌어와 생성 프롬프트에 주입한다.**

1. **단일 카탈로그(`core/sql/catalog.py`, 순수 데이터·LangGraph 무관)**: business DB의 조회 표면을 선언한다 — 테이블·컬럼, 카테고리형 컬럼의 허용값(enum/형식), PII 플래그. `core/`에 두어 레이어 규칙(LangGraph 불가지)을 지키고, `scripts/`와 `app/graph/` 양쪽이 import한다.
2. **시드와 출처 공유**: `scripts/seed_business.py`가 이미 들고 있는 축 상수(`_SALES_PERIODS`, `_SALES_DEPTS`, `_DEPT_PRODUCT`, position 리터럴)를 카탈로그에서 가져오도록 전환 → 시드와 힌트가 같은 source of truth.
3. **PII 불변식**: PII 컬럼(`name`, `salary`, `email`)은 스키마 목록엔 남기되(조회 가부는 게이트가 통제) **값 힌트는 절대 생성하지 않는다**. 행 내용 덤프는 게이트·FGA가 돌기 전 PII 누수가 되므로 금지하며, 힌트는 비-PII·저카디널리티 카테고리형 컬럼으로 한정한다.
4. **drift 방지 테스트**: "DB 실제 distinct 값 ⊆ 카탈로그 허용값"을 검증하는 테스트를 둔다. 새 값(특히 향후 늘어날 `position`)을 시드에 추가하고 카탈로그 갱신을 잊으면 테스트가 실패해 힌트 동기화를 강제한다.

## Rationale

- **실패 모드가 value mismatch로 특정됨** → 처방은 스키마 보강이 아니라 *값* 힌트다. few-shot(다른 실패 모드용)은 범위 밖.
- **이 DB는 결정론적 소규모 시드**라 동적 조회의 "최신성" 이점이 사실상 0. 반면 인프라·PII allowlist 강제 비용은 실재 → YAGNI로 정적 카탈로그 채택.
- **drift가 정적 방식의 유일한 약점**인데, 사용자가 "`department`는 거의 안 변하지만 `position`은 늘어날 가능성이 높다"고 명시 → 단일 카탈로그 + 검증 테스트로 그 약점을 구조적으로 제거하는 게 정확한 대응.
- **PII는 게이트(ADR-0016)의 존재 이유**다. 힌트가 그 경계를 우회하지 않도록 PII 컬럼 값 미노출을 불변식으로 못 박는다.

## 미해결 / 후속

- **OpenFGA 모델 기반 테이블 접근권한**: 향후 FGA 권한(ADR-0015) 모델에 따라 신원별로 조회 가능한 *테이블 자체*가 달라질 전망. 이 경우 카탈로그는 신원에 따라 동적으로 필터된 뷰를 프롬프트에 노출해야 하며(권한 없는 테이블은 힌트에서 제외), 본 ADR의 정적 전체-카탈로그를 확장해야 한다. **별도 ADR로 분리**한다.
- few-shot 예시 도입 여부 — 스키마/조인 오해(실패 모드 2)가 관측되면 그때 별도 검토.
- 동적 distinct 조회로의 전환 트리거 — 실제 운영 DB(시드 아님)로 확장 시 재평가.

## 영향받는 결정

- [ADR-0016](ADR-0016-identity-risk-sql-gate.md) — 본 ADR의 PII 미노출 불변식이 그 게이트의 통제 경계를 보강한다.
- [ADR-0020](ADR-0020-sql-gate-prerequisite-infra.md) — 본 ADR의 카탈로그가 그 시드(`seed_business.py`)와 출처를 공유한다.
- [ADR-0015](ADR-0015-fga-public-private-super-reader.md) — 후속(테이블 접근권한) 확장의 권한 모델 기반.
