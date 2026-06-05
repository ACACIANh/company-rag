# 직원 30명 확장 + 부서별 팀장 설계

> 날짜: 2026-06-05
> 관련 ADR: ADR-0014(시드 재구성), ADR-0046(부서 관리자 위임), ADR-0051(permission 노드 분리)

## 목표

데모/시연 데이터 볼륨을 키운다.
- 직원 수: 12명 → **30명** (모두 실계정: 로그인 + FGA 멤버십 + `business.employees` 행)
- **7개 실부서 각각에 팀장(dept_admin) 1명**을 둔다.
- 팀장을 FGA 위임 권한(`dept_admin`)뿐 아니라 `employees.position` 컬럼에도 `팀장`으로 표시한다.

## 배경 / 결정

- "DB 행만 늘리는" 분리(decouple) 안 대신 **전부 실계정** 안을 채택. 사유: 구조가 더 바뀔 가능성이 낮고, 모든 직원이 로그인·권한 테스트 대상이 되는 편이 일관적. 비용(yaml ~230줄, FGA 튜플 ~2배)은 수용 가능, 성능 영향 없음.
- 시드 스크립트(`seed_business.py`, `seed_fga.py`)는 **완전히 데이터 주도** — `users.yaml`을 순회한다. 따라서 계정을 추가하고 `dept_admin_of`를 붙이면 employees 30행 + 팀장 FGA 튜플이 **코드 변경 없이** 자동 생성된다.
- 단, 팀장을 `employees.position`에 표시하려면 카탈로그/시드 position 로직에 소폭 변경이 필요하다(아래 4번).

## 1. 계정 구성 (총 30개)

기존 12개 계정 그대로 유지(admin 포함). 신규 18개 추가, 모두 단일 부서·`roles:[user]`.

아래 "부서 총원"은 `employees.department` 기준 = **primary 부서**(`_primary_department` = `departments[0]`)다. 겸직자는 첫 부서 1곳에만 집계된다(junseo→개발, chaewon→영업, taeyang→인사). 그래서 SQL `GROUP BY department COUNT`가 이 표와 일치한다.

| 부서(primary) | 기존 | 신규 | 총원 |
|------|:--:|:--:|:--:|
| 개발 | 2 (jisoo, junseo) | +4 | 6 |
| 제품 | 1 (dohyeon) | +3 | 4 |
| 영업 | 2 (minho, chaewon) | +3 | 5 |
| 인사 | 2 (minjun, taeyang) | +2 | 4 |
| 재무 | 1 (jiyoung) | +2 | 3 |
| 법무 | 1 (subin) | +2 | 3 |
| 디자인 | 1 (yujin) | +2 | 3 |
| 임원 | 1 (admin) | 0 | 1 |
| 미배정 | 1 (seoyeon) | 0 | 1 |
| **합계** | **12** | **+18** | **30** |

### 신규 18명 로스터

`password` = `<username>123`, `user_id` = `user-<username>`, `email` = `<given>.<surname>@techcorp.example` (기존 스타일 일치).

| # | 부서 | display_name | username | email |
|---|------|------|------|------|
| 1 | 개발 | 김도윤 | dowoon | dowoon.kim@techcorp.example |
| 2 | 개발 | 이서진 | seojin | seojin.lee@techcorp.example |
| 3 | 개발 | 박하준 | hajun | hajun.park@techcorp.example |
| 4 | 개발 | 정시우 | siwoo | siwoo.jung@techcorp.example |
| 5 | 제품 | 최예준 | yejun | yejun.choi@techcorp.example |
| 6 | 제품 | 강주원 | juwon | juwon.kang@techcorp.example |
| 7 | 제품 | 윤지호 | jiho | jiho.yoon@techcorp.example |
| 8 | 영업 | 임은우 | eunwoo | eunwoo.lim@techcorp.example |
| 9 | 영업 | 한유찬 | yuchan | yuchan.han@techcorp.example |
| 10 | 영업 | 오선우 | sunwoo | sunwoo.oh@techcorp.example |
| 11 | 인사 | 이수아 | sua | sua.lee@techcorp.example |
| 12 | 인사 | 박지유 | jiyu | jiyu.park@techcorp.example |
| 13 | 재무 | 정세린 | serin | serin.jung@techcorp.example |
| 14 | 재무 | 최예린 | yerin | yerin.choi@techcorp.example |
| 15 | 법무 | 강민서 | minseo | minseo.kang@techcorp.example |
| 16 | 법무 | 윤채은 | chaeeun | chaeeun.yoon@techcorp.example |
| 17 | 디자인 | 신지안 | jian | jian.shin@techcorp.example |
| 18 | 디자인 | 김하린 | harin | harin.kim@techcorp.example |

username·display_name 모두 기존 12명과 충돌 없음(확인 완료).

## 2. 팀장 7명 (`dept_admin_of`)

부서별 기존 단일소속 계정에 `dept_admin_of: [<부서>]`를 부여 → FGA `user:X admin department:Y` 튜플.

| 부서 | 팀장 | 상태 |
|------|------|------|
| 개발 | 김지수(jisoo) | 기존 유지 |
| 제품 | 최도현(dohyeon) | 신규 부여 |
| 영업 | 강민호(minho) | 신규 부여 |
| 인사 | 이민준(minjun) | 신규 부여 |
| 재무 | 윤지영(jiyoung) | 신규 부여 |
| 법무 | 임수빈(subin) | 신규 부여 |
| 디자인 | 정유진(yujin) | 신규 부여 |

겸직자(junseo/chaewon/taeyang)는 부서 모호성 때문에 팀장 제외. 팀장 권한 의미는 ADR-0046/0051(자기 부서 멤버십 위임 + 자기 부서 보유 permission 배정).

## 3. 변경 파일

- **`config/users.yaml`**: 신규 18개 계정 추가 + 기존 6개 계정(dohyeon/minho/minjun/jiyoung/subin/yujin)에 `dept_admin_of` 추가.
- **`core/sql/catalog.py`**: `POSITIONS`에 `"팀장"` 추가 → `["CTO", "팀원", "팀장"]`. `CATEGORICAL_VALUES["business.employees.position"]`는 `POSITIONS`를 참조하므로 값 힌트(NL→SQL)에 자동 반영.
- **`scripts/seed_business.py`**: `build_employee_rows`의 position 결정 로직 변경.
  - 기존: `position = POSITIONS[0] if is_exec else POSITIONS[1]`
  - 변경: `is_exec → "CTO"`, `user.get("dept_admin_of") → "팀장"`, `else → "팀원"`.

`seed_fga.py`는 변경 없음(`dept_admin_of` 처리 로직 이미 존재).

## 4. 테스트

- `tests/scripts/test_seed_business.py`: position 로직 테스트 추가 — dept_admin_of 보유 user → `"팀장"`, c_level → `"CTO"`, 평직원 → `"팀원"`. 기존 카운트 테스트는 fixture 기반이라 영향 없음.
- `tests/scripts/test_seed_fga.py`: 기존 `dept_admin_of` 튜플 테스트로 커버됨. 추가 불필요.
- `core/sql/catalog.py` 변경에 대한 회귀: 기존 `test_catalog_*`는 equipment만 검사 → 영향 없음.

## 5. 적용(re-seed) 절차

코드/yaml 변경 후 실제 데이터 반영은 DB·OpenFGA가 떠 있는 환경에서:
1. `cd backend && .venv/bin/python -m scripts.seed_business` → employees 30행 재시드(TRUNCATE 후 재삽입).
2. `.venv/bin/python -m scripts.seed_fga` → 멤버십·팀장 튜플 추가(멱등). 기존 store와 정합화가 필요하면 `--prune`(주의: 운영 중 추가분도 삭제).

> 이 환경에 DB/FGA가 떠 있지 않으면 시드 실행은 사용자 환경에서 수행한다. 단위 테스트(`pytest`)는 DB 없이 통과 가능.

## 비목표 (YAGNI)

- 합성 직원의 개별 문서 소유/폴더 권한 부여 — 하지 않음(멤버십·테이블 권한은 부서 단위로 이미 커버).
- `business.equipment.assigned_to` 신규 직원 매핑 — 기존 8개 자산 그대로(기존 user_id 참조 유지).
- 매출(sales) 데이터 변경 — 부서 단위라 인원수와 무관.
