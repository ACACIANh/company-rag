# 설계: 권한(permission)을 부서에서 분리 — 1급 노드 도입

> **Status**: ⚪ 제안됨 (브레인스토밍 합의 완료, 구현 계획 대기)
> **날짜**: 2026-06-05
> **신규 ADR**: ADR-0051 (이 spec 승인 시 작성)
> **영향 ADR**: 0046 대체, 0015·0050 개정, 0033 명명 근거

## 1. 문제

권한 부여가 **부서 멤버십 부여와 강제로 결합**돼 있다. "민준에게 인사 문서 하나를 보여주고 싶다"가 시스템상 "민준을 인사에 통째로 넣기"가 되고, 그 결과 인사의 **모든 폴더 + 테이블 + SQL 권한 + 조직상 의미 + 부서 admin 위임 대상**이 함께 딸려온다. 최소권한 원칙 위반.

결합이 박혀 있는 곳은 사실상 **폴더(folder) 한 곳**이며, 3중 장벽으로 강제된다:

| 장벽 | 위치 | 내용 |
|---|---|---|
| 모델 (구조적 불가) | `fga/model.fga:20` | `define dept_viewer: [department#member]` — 폴더 권한 주체로 부서만 허용. `user:민준 dept_viewer folder:/hr`는 타입 위반으로 거부 |
| Validator (정책 차단) | `core/fga/permission_validator.py:114-122` | folder dept_viewer subject를 `department:X#member`로만 해석, 개인이면 `None` |
| NL 프롬프트 (의도 번역) | `app/graph/prompts.py:169-173` | "유저에게 폴더 열람권" → "부서 멤버십 부여"로 강제 번역 |

**이미 분리된 곳** — 테이블/SQL은 모델상 개인 부여가 이미 가능하다(`table.dept_viewer: [user, department#member, role#member]` — `model.fga:52`; capability도 일부 `user` 허용 — `model.fga:42-45`). 단 운영(시드)은 여전히 부서 단위로만 부여한다.

## 2. 목표 / 비목표

**목표**
- 부서 가입 **없이** 특정 권한 묶음을 개인(user)에게 직접 부여 가능하게 한다.
- 권한 = **폴더 + 연관 테이블 + 연관 SQL을 묶는 업무 단위**. "연관 리소스도 함께 딸려온다"는 동작은 유지하되, 그 단위를 부서 멤버십에서 떼어낸다.
- private 폴더 보장(공개 상속 차단, c_level 관통)을 그대로 보존한다.
- 검색/실행 코드 경로(retrieve·gate·client 호출 시그니처)는 **건드리지 않는다**.

**비목표**
- 폴더/테이블을 단일 OpenFGA type으로 물리 통합하지 않는다(과추상화 — §6).
- 권한을 폴더 1개 단위까지 잘게 쪼개는 것을 기본으로 삼지 않는다. 기본은 업무 묶음(부서 1:1 승계), 세밀 권한은 필요 시 추가 정의(혼합 입도).
- 부서·역할(role)·private·super_reader 등 기존 축을 제거하지 않는다.

## 3. 핵심 설계: `permission` 1급 노드

기존 `department#member`를 각 리소스 relation에 **직접 주입**하던 구조를, **`permission#holder`를 한 단계 경유**하도록 바꾼다.

```
permission:인사  ──holder──  department:인사#member   (부서는 기본 탑재)
                   └─holder──  user:민준                  (개인 직접 — 부서 무관)
       │
       ├─ gates ─→ folder:/company/hr      (문서)
       ├─ gates ─→ table:employees         (테이블)
       └─ (holder) ─→ capability:sql        (연관 SQL 등급)
```

`holder: [user, user:*, department#member, role#member]` 한 줄이 **부서·개인·전직원·역할 경로를 동시에** 보장한다. 민준은 인사 멤버가 아니어도 `permission:인사`만 has로 가지면 인사 묶음 전체에 접근한다. permission 이름은 부서명과 통일하고(`permission:인사` = `department:인사`), 비-부서 묶음만 `기본`(전 직원)·`전사`(c_level)로 둔다.

### 3.1 모델 변경 (`fga/model.fga` + `model.json`)

신설:
```
type permission
  relations
    define holder: [user, user:*, department#member, role#member]
```

folder — `dept_viewer`/`dept_access`를 **개명**(§5)하고 permission 경유 TTU로 전환:
```
type folder
  relations
    define parent: [folder]
    define gated_by: [permission]                       # 신설: 이 폴더를 여는 권한(들)
    define viewer: holder from gated_by                  # (구 dept_viewer) 부서직접 → permission 경유
    define access: viewer or access from parent          # (구 dept_access)
    define public_viewer: [user:*]                       # 유지
    define public_access: public_viewer or public_access from parent
    define private_flag: [user:*] or private_flag from parent   # 유지 — private 보장
    define super_reader: [role#member] or super_reader from parent   # 유지 — c_level 관통
    define can_read: super_reader or access or (public_access but not private_flag)
```

table — 동형 전환:
```
type table
  relations
    define gated_by: [permission]                        # 신설
    define viewer: holder from gated_by                  # (구 dept_viewer)
```

capability — 모든 SQL 권한을 permission 경유로 통일. 메타권한 `justify_grant`만 예외(권한관리는 역할·부서 직접 유지):
```
type capability
  relations
    define allow_select:          [permission#holder]
    define justify_select:        [permission#holder]
    define justify_bulk_select:   [permission#holder]
    define justify_update_delete: [permission#holder]
    define justify_ddl:           [permission#holder]
    define justify_grant:         [user, department#member, role#member]   # 메타권한 — permission 비포함(권한관리)
```

> **`can_read` 합성식·검색 코드 불변**: 주체가 부서든 permission이든 `ListObjects(user:X, can_read, folder)`는 동일하게 동작한다. FGA가 `user → permission#holder → gated_by → folder` 체인을 내부 해소한다. `retrieve.py`/`gate.py`/`client.py` 호출 시그니처는 손대지 않는다.

### 3.2 시드 / 데이터 (`scripts/seed_fga.py`, `config/`)

권한 정의를 SSOT로 분리한다. **permission 이름은 부서명과 통일**(`permission:인사` = `department:인사`). 비-부서 묶음은 `기본`(전 직원)·`전사`(c_level). **`config/permissions.yaml` 신설**:
```yaml
permissions:
  기본:                               # 전 직원 — holder: user:*
    sql:     [allow_select, justify_bulk_select]
  인사:
    folders: [/company/hr]
    tables:  [employees]
  재무:
    folders: [/company/finance]
    tables:  [employees, sales]
  개발:
    folders: [/company/engineering/ops]
    tables:  [employees, sales, equipment]
    sql:     [justify_update_delete]  # 개발 특화 (기존 _CAPABILITY_GRANTS)
  영업:
    tables:  [sales]
  제품:
    tables:  [sales]
  법무:
    folders: [/company/legal]
  전사:                               # c_level — holder: role:c_level#member
    tables:  [employees, sales, equipment]
    sql:     [justify_update_delete]
  # 묶음 단위 = 부서 1:1 승계(기존 동작 무손실). 세밀 권한은 여기에 새 항목으로 추가.
  # 폴더 전사열람은 super_reader(role) 유지 — permission:전사는 테이블·SQL만 담당.
```

holder 배정:
```
permission:기본    holder user:*                     # 전 직원
permission:인사  holder department:인사#member    # 부서 1:1
permission:전사    holder role:c_level#member         # c_level
...
```

`_build_tuples`가 생성하는 튜플 형태 변화:
- (구) `department:인사#member  dept_viewer  folder:/company/hr`
- (신) `permission:인사  holder  department:인사#member`
      `folder:/company/hr  gated_by  permission:인사`
      `table:employees  gated_by  permission:인사`
- (구) `user:*  allow_select  capability:sql`
- (신) `permission:기본  holder  user:*`  +  `permission:기본#holder  allow_select  capability:sql`
- 개인: `permission:인사  holder  user:민준`  (부서 무관 직접 부여)

모든 SQL 권한이 permission 경유로 통일된다 — 전 직원 기본 SELECT는 `permission:기본`(holder `user:*`), 부서특화·전사 쓰기는 해당 permission이 담는다.

### 3.3 위임 정책 (ADR-0046 대체 — "C레벨 + 각 팀장")

두 종류의 grant를 분리한다:

| 행위 | c_level | 부서 팀장(`department.admin`) |
|---|---|---|
| **정의** `permission gated_by resource` / `permission#holder capability` | ✅ | ❌ — 새 리소스 연결 = 부서 경계 누수 → 차단 |
| **배정** `user holder permission:X` (개인 부여) | ✅ 전체 | ✅ **자기 부서가 holder인 permission에 한정** |
| 부서 멤버십 `user member department` | ✅ | ✅ 자기 부서 (기존 유지) |

→ 팀장은 새 리소스를 권한에 못 엮고(정의 불가), 이미 자기 부서가 보유한 권한을 개인에게 떼주기만 한다. ADR-0046의 누수 차단 정신을 permission 모델로 이식하며, 위임 유연성(팀장 자율)을 확보한다.

게이트 승격 판정(`tool_gate.py` + `permission_tool.py`):
- 현행 `delegated_membership_dept`(멤버십만)에 더해, planned_action이 `grant <user> holder permission:X`이고 요청자가 **X를 holder로 보유한 부서의 admin**이면 `DECISION_DENY → JUSTIFY_AND_APPROVE`로 승격한다(사유 기재 후 실행). "X를 보유한 부서" 판정은 FGA `check(department:Y#member, holder, permission:X)` + `check(user:요청자, admin, department:Y)`로 확인.

## 4. 영향 범위

**바꾸는 곳**
- `fga/model.fga` + `fga/model.json` — permission type 신설, folder/table TTU 전환·개명, capability 주체 확장
- `scripts/seed_fga.py` — `_build_tuples` permission 경유 생성, `_TABLE_GRANTS`·`_CAPABILITY_GRANTS` permission화, `config/permissions.yaml` 로드
- `config/permissions.yaml` (신설), `config/folders.yaml` (dept_viewers → permission 매핑 이관)
- **부서 id 정규화**: `인사팀→인사` 등 6개 부서명에서 "팀" 제거 — permission 이름과 완전 통일(`permission:인사` = `department:인사`). `config/users.yaml`(departments/dept_admin_of)·`folders.yaml`·`seed_fga.py`(`_TABLE_GRANTS`/`_CAPABILITY_GRANTS`)·`prompts.py` 예시 일괄
- `core/fga/permission_validator.py` — 화이트리스트 재정의: `holder`(배정)·`gated_by`(정의) relation 추가, 개인 permission 부여 허용, 개명 반영
- `app/graph/prompts.py` — `PERMISSION_PARSE_PROMPT`: "유저→부서멤버십" 번역 규칙(169-173) 폐기, holder/gated_by 출력 규칙 추가
- `app/graph/tools/permission_tool.py` — `delegated_membership_dept`에 permission 배정 위임 판정 추가, 도구 설명 갱신
- `app/graph/nodes/tool_gate.py` — 위임 승격 분기에 permission 배정 케이스 추가

**안 바꾸는 곳** (회귀 표면 최소화)
- `app/graph/nodes/retrieve.py`, `core/sql/gate.py` 호출부, `app/graph/nodes/permission.py`, `core/fga/client.py` 검색 시그니처(`get_readable_folders` 등), FGA PostgreSQL TTL 캐시 구조

**마이그레이션: Big bang** — 기존 `dept_viewer: [department#member]` 직접연결을 제거하고 permission 전면 전환. 데모 시드라 데이터가 적어 병행 유지보다 깔끔. 절차: 모델 교체 → `seed_fga.py --prune`로 stale 튜플 정리 → 재시드.

## 5. relation 개명 (ADR-0033 명명원칙)

`folder.dept_viewer`/`table.dept_viewer`는 이제 "부서 전용"이 아니므로 의미가 어긋난다. 외부 경계 노출 이름은 역할(role)을 드러내야 한다는 ADR-0033에 따라:

| 구 이름 | 신 이름 | 근거 |
|---|---|---|
| `folder.dept_viewer` | `folder.viewer` | permission holder로부터 오는 직접 열람권 — 주체 종류(부서) 비노출 |
| `folder.dept_access` | `folder.access` | viewer + 트리 상속 |
| `table.dept_viewer` | `table.viewer` | 동일 |

`super_reader`·`public_viewer`·`private_flag`·`can_read`는 의미가 유지되므로 개명하지 않는다. 개명은 `model.fga`·`seed_fga.py`·`permission_validator.py`·`prompts.py`의 문자열 상수에 일괄 반영.

## 6. 설계 판단 기록

- **folder/table 물리 통합은 과추상화**: folder는 트리 상속·public·private라는 고유 구조를, table은 평면 구조를 가진다. 단일 type으로 합치면 table이 안 쓰는 `parent`/`private_flag`를 떠안아 모델이 지저분해지고 누수 표면이 커진다. **`permission` 노드가 이미 추상화 레이어** 역할을 하므로(이질적 리소스를 "권한"으로 묶음) resource를 또 합칠 실익이 없다.
- **권한 입도 = 업무 묶음(부서 1:1 기본 + 혼합)**: 사용자 요구가 "연관 테이블·SQL도 함께"이므로 폴더 1개 단위 세밀화는 기본이 아니다. 기본은 부서가 보던 묶음을 permission으로 1:1 승계(마이그레이션 기계적), 개인 최소권한이 필요한 경우만 세밀 permission을 추가 정의.
- **private 보장 직교 유지**: `private_flag`/`super_reader`는 permission과 무관하게 그대로 둔다. private 폴더는 permission을 명시 보유한 holder만 보고 public 상속으로 새지 않는다.

## 7. ADR 영향

- **ADR-0051 (신규)**: permission 1급 노드 분리 — 본 spec의 결정 기록.
- **ADR-0046 → 🟣 대체됨**: 위임 단위가 "부서 멤버십만"에서 "permission 배정(정의/배정 분리)"으로 재설계. `individual_viewer` 비목표 선언이 뒤집힘.
- **ADR-0015 개정**: folder `dept_viewer: [department#member]` → `viewer: holder from gated_by`. pre-filter 메커니즘 자체는 불변.
- **ADR-0050 개정 + 드리프트 정리**: 본문 "테이블 개인 부여 불가"가 라이브 모델(`[user, ...]`)과 모순 상태. permission 전환과 함께 정합화.
- **ADR-0033**: dept_viewer → viewer 개명의 명명 근거.

## 8. 검증 / DoD

1. **단위 테스트**:
   - `permission_validator`: 개인 permission 배정(`user holder permission:X`) 통과, 팀장 권한 밖 정의(`permission gated_by folder`) 거부, 개명 relation 검증.
   - 위임 승격: 팀장이 자기 부서 permission을 개인에 배정 시 JUSTIFY 승격, 타 부서 permission은 DENY.
2. **FGA 통합/모델 검증**: `user:민준 holder permission:인사`만으로 `can_read folder:/company/hr` = true(부서 미가입), private 누수 없음, big bang 재시드 후 기존 부서원 접근 동등성.
3. **회귀**: `tests/eval/runner.py` 점수 — 기존 부서 기반 접근 시나리오 점수 유지(하락 시 원인 명시).
4. **ADR**: ADR-0051 작성 + 0046/0015/0050 상태·본문 갱신 + `python -m scripts.gen_adr_index`.

## 9. 미해결 / 리스크

- **`permission:전사` vs `super_reader` 경계**: 폴더 전사열람은 기존 `super_reader`(role 경유) 유지, 테이블·SQL만 `permission:전사`가 담당. 이 이원화가 혼란을 주지 않도록 plan에서 주석·시드 명확화.
- **위임 승격 FGA 왕복 비용**: permission 배정 위임 판정에 check 2회 추가. 게이트 경로라 캐시 비대상 — 허용 가능 수준이나 plan에서 확인.
- **개명 누락 위험**: dept_viewer 문자열이 코드·테스트·문서에 분산. big bang 시 일괄 치환 후 grep 잔재 확인 필요.
- **부서 id 변경 영향**: `인사팀→인사` 정규화가 데모 시나리오(minjun 인사 등)·프론트 표시·감사 로그에 미치는 영향 확인. Big bang 재시드로 옛 `department:인사팀` 튜플은 `--prune`으로 정리. (표시명을 "인사팀"으로 유지할 필요가 있으면 id≠표시명 분리를 plan에서 재검토.)
