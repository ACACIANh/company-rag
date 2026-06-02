# TechCorp 시드 데이터 전면 재구성 — Design

> ADR-0014(방향 결정·🟡보류)의 구체 spec. 선행조건 ADR-0015(FGA 4축 모델, 🟢적용완료) 충족으로 보류 해제.

**Date**: 2026-06-02
**Status**: 설계 승인됨 — 구현 대기

## 목적

실사용 환경처럼 체감하며 테스트하기 위해 부서·사원·문서를 대폭 늘린다. 1차 검증 목적은 **균형** — 권한 경계(4축 FGA)와 검색 품질(multi_query·RRF·리랭킹)이 둘 다 실사용 규모에서 드러나도록 한다.

현재(기존): 문서 15 / 폴더 3+ops / 사용자 4. 목표: 부서 7 + 전사공통 / 사원 12 / 문서 ~46.

## 비목표 (YAGNI)

- FGA 모델(`fga/model.fga`·`model.json`) 변경 — type 수준이라 인스턴스 증가와 직교. 불변.
- pre-filter 로직(`build_pg_filter` 정확매칭) 변경 — ADR-0015에서 확정. 불변.
- eval 러너(`runner.py`)·evaluator 구조 변경 — 불변. questions.yaml 데이터만 교체.

## 섹션 1: 폴더 트리 + 권한 레이아웃 (B안 — private 다층형)

```
/company                    public + super_reader[c_level]   # 전 직원 + 임원
├── common/                 (상속 public)                    # 전사공통
├── engineering/            (상속 public)
│   └── ops/                private + dept_viewers[engineering]   # 서브트리 private(상속 차단 자극)
├── product/                (상속 public)
├── design/                 (상속 public)
├── sales/                  (상속 public)
├── hr/                     private + dept_viewers[hr]
├── finance/                private + dept_viewers[finance]
└── legal/                  private + dept_viewers[legal]
```

- 부서 7개: engineering · product · design · sales · hr · finance · legal.
- 전사공통 common(부서 아님, public).
- private 서브트리 4개: ops · hr · finance · legal.
  - **ops**: public 부모(engineering) 밑 서브트리 private → ADR-0015 "private_flag 상속 차단" 경계를 직접 자극.
- `/company`에 public + super_reader[c_level] 단 한 번 부여 → 하위 전 폴더 상속.

`config/folders.yaml`이 튜플 생성의 단일 소스. base_path=`/company` prefix.

## 섹션 2: 사원 12명

기존 4명(alice=engineering, bob=hr, carol=무소속, admin=c_level) 매핑을 **그대로 보존**해 fixture churn을 최소화한다. 나머지 8명은 additive.

| # | username | departments | fga_roles | 열람 범위 | 분류 |
|---|---|---|---|---|---|
| 1 | admin | — | c_level | 전사(private 관통) | super_reader·보존 |
| 2 | alice | engineering | — | public + eng/ops | 단일·보존 |
| 3 | bob | hr | — | public + hr | 단일·보존 |
| 4 | carol | (없음) | — | public만 | 권한0·보존 |
| 5 | dave | product | — | public | 단일 |
| 6 | erin | design | — | public | 단일 |
| 7 | frank | sales | — | public | 단일 |
| 8 | grace | finance | — | public + finance | 단일 |
| 9 | heidi | legal | — | public + legal | 단일 |
| 10 | ivan | engineering, product | — | public + eng/ops | 교차(public+서브트리 private) |
| 11 | judy | sales, finance | — | public + finance | 교차(public+private) |
| 12 | karl | hr, legal | — | public + hr + legal | 교차(두 private) |

구성: c_level 1 · 무소속 1 · 교차부서 3 · 단일부서 7.

비밀번호는 기존 컨벤션(`<username>123`) 따른다. user_id는 `user-<username>`.

## 섹션 3: 문서 코퍼스 (~46개)

기존 15개는 폴더가 맞으면 재사용(★), 나머지 31개 신규. 문서 충실도 = 기존 수준의 실내용(요약 스텁 아님).

| 폴더 | 수 | 목록 (★=기존 재사용) |
|---|---|---|
| common | 10 | ★benefits, ★expense-policy, ★meeting-culture, ★onboarding, ★remote-work-policy, ★security-policy, ★team-structure, ★tools-and-access, ★vacation-policy, code-of-conduct |
| engineering | 6 | ★api-spec, ★code-review-guide, ★engineering-standards, architecture-overview, tech-stack, oncall-rotation |
| engineering/ops | 3 | ★deployment-guide, ★incident-response, monitoring-runbook |
| product | 5 | product-roadmap, prd-template, release-process, feature-flags, user-research |
| design | 4 | design-system, brand-guidelines, ux-principles, accessibility |
| sales | 5 | sales-playbook, pricing, crm-process, contract-template, quota-policy |
| hr | 5 | ★performance-review, hiring-process, compensation-bands, leave-of-absence, disciplinary-policy |
| finance | 4 | budget-process, expense-approval, procurement, financial-reporting |
| legal | 4 | nda-policy, data-privacy, contract-review, ip-policy |

합계 **46** (기존 15 재사용 + 신규 31). team-structure.md는 새 조직(12명·7부서)을 반영해 내용 갱신.

### 의도된 검색 함정 (동음이의 + 권한 분산)

같은 키워드가 public·private 폴더에 분산되어 pre-filter 정확매칭 + 리랭킹을 동시 자극:

- **"계약"** → sales/contract-template(public) + legal/contract-review(private). carol은 sales만, karl은 legal까지 → 권한별 결과 차이.
- **"예산/비용"** → common/expense-policy(public) + finance/budget-process·expense-approval(private).
- **"보안/개인정보"** → common/security-policy(public) + legal/data-privacy(private).
- **"리뷰"** → engineering/code-review-guide + hr/performance-review + legal/contract-review (세 부서 동음이의).

## 섹션 4: eval / fixture 이관 계획

### eval/questions.yaml (현 36 → 약 30)

- **doc_search ~24문항**: 신규 코퍼스 기준. 새 부서(product·design·sales·finance·legal) 커버 + 검색 함정 4종을 명시 문항으로 포함.
- **tool_call 6문항 유지**: 코퍼스 독립(라우팅 분류) — 불변.
- **baseline**: committed 파일 없음(러너가 aggregate를 출력, 개발자 수기 비교). 재작성 후 `runner.py` 실행 → recall@k·mrr·kw 재기록. 검색 함정으로 mrr 하락 가능 → "권한·동음이의 함정 추가에 따른 의도된 변화"로 ADR-0014에 원인 명시(DoD 규칙2).

### 테스트 fixture

보존 매핑 덕에 대부분 생존. 깨질 것은 **개수·목록 단정**:

- `tests/scripts/test_seed_fga.py` — 튜플 개수·폴더 목록 단정 → 새 트리로 갱신.
- `tests/app/graph/nodes/test_permission_node.py` · `tests/app/test_rag_with_fga.py` — "alice가 보는 폴더 집합" 등 단정 → 신 트리 반영. **교차부서(ivan/judy/karl)·무소속(carol)·super_reader 관통(admin) 권한 매트릭스 케이스 신규 추가**.
- `conftest.py` — 시드 사용자 목록 fixture 갱신.

권한 매트릭스 검증은 eval이 아니라 단위테스트 책임(eval 러너는 권한 무관).

### 산출물 순서

1. `config/users.yaml` · `config/folders.yaml` 작성
2. `docs/company/**` 문서 작성(신규 31 + team-structure 갱신)
3. `tests/eval/questions.yaml` 재작성
4. 테스트 fixture 갱신 + 권한 매트릭스 케이스 추가
5. `scripts/seed_fga.py` 재실행 → `scripts/build_index.py` 재인덱싱
6. 단위테스트 전체 통과 확인
7. eval 재기록 → ADR-0014에 신 baseline 기록
8. ADR-0014 Status 🟡보류 → 🟢적용완료 갱신 + `python -m scripts.gen_adr_index`

## 검증 (DoD)

1. 단위테스트 추가(교차부서·무소속·super_reader 권한 매트릭스).
2. `tests/eval/runner.py` 회귀 점수 재기록(하락 시 원인 명시).
3. 새 의존성·패턴 없음 → 신규 ADR 불필요. ADR-0014 Status·baseline 갱신만.
