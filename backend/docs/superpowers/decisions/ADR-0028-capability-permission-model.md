# ADR-0028: SQL 게이트를 OpenFGA capability 모델로 통일 (SP2a)

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: 권한 관리 도구(SP2, `fga_grant_revoke`)를 얹으려 하니, SQL 권한이 "부여 가능한 권한"이 아니어서 막힌다. SQL 게이트는 OpenFGA가 아니라 `core/sql/gate.py`의 `tier×risk` 매트릭스에 하드코딩돼 있어 코드 수정으로만 바뀐다. 디렉토리 권한(`folder.can_read`)은 이미 OpenFGA로 부여 가능한데, SQL 권한만 다른 메커니즘 위에 있는 비대칭을 해소한다. **SP2를 분해해 이번 스펙은 덩어리 1(권한 모델 통일)만 다룬다. grant/revoke 도구 자체는 SP2b로 분리.**

## Options

### 결정 1 — "부여 가능한 권한" 개념 도입 방향
| 선택지 | 트레이드오프 |
|--------|------------|
| **SQL 권한을 OpenFGA로 통일** | SQL 권한을 capability로 모델링 → 디렉토리·SQL 모두 동일하게 부여 가능. 게이트가 Check로 통일. 모델 재설계 필요 |
| 디렉토리 권한만 도구화 | 작은 변경. 단 "부여 가능한 권한" 통일 개념 포기, SQL은 영영 하드코딩 |

### 결정 2 — 권한을 OpenFGA로 표현하는 방식
| 선택지 | 트레이드오프 |
|--------|------------|
| **권한을 relation으로 (명시적)** | 권한 종류를 `model.fga` relation으로 고정. 타입세이프·문서화·오타 차단. 새 권한 추가 시 스키마 변경(드묾) |
| 권한을 타입(객체)으로 | 권한이 인스턴스. 런타임 추가 가능·도구 단순. 대신 오타 유령권한 위험·모델이 문서가 아님 |

### 결정 3 — 3-state 게이트를 boolean Check로 표현
| 선택지 | 트레이드오프 |
|--------|------------|
| **2층 relation (`allow_*`/`justify_*`)** | 위험도당 relation 2개. 매트릭스 100% 튜플로 재현, 게이트 정책 전부 데이터 → 재배포 없이 운영·셀별 차등 미래대응. relation 2배·Check 2번 |
| 1층 + 정책코드 절충 | `can_*`만 OpenFGA, ALLOW/JUSTIFY 경계는 코드 상수. 단순하나 "절반만 통일"·셀별 차등 불가 |

### 결정 4 — 부수 결정
| 항목 | 선택 |
|------|------|
| 시드 기본부여 정책 위치 | `seed_fga.py` 내 상수 (`capabilities.yaml` 신설 대신) |
| `gate.py`의 fga 의존 | `CapabilityChecker` Protocol 약결합 (FGAClient 직접 import 안 함) |

## Decision

**결정 1: SQL 권한을 OpenFGA로 통일.**
**결정 2: 권한을 relation으로 (명시적).**
**결정 3: 2층 relation (`allow_*`/`justify_*`).**
**결정 4: 시드 정책은 `seed_fga.py` 상수, `gate.py`는 `CapabilityChecker` Protocol 약결합.**

### 구현 범위 (SP2a)

#### ① `fga/model.fga` — `capability` 타입 신설
```
type capability
  relations
    define allow_select:          [user:*, department#member, role#member]
    define justify_select:        [user:*, department#member, role#member]
    define allow_bulk_select:     [user:*, department#member, role#member]
    define justify_bulk_select:   [user:*, department#member, role#member]
    define allow_update_delete:   [user, department#member, role#member]
    define justify_update_delete: [user, department#member, role#member]
    define allow_ddl:             [user, department#member, role#member]
    define justify_ddl:           [user, department#member, role#member]
```
- 인스턴스는 `capability:sql` 하나. 디렉토리 권한(`folder.can_read`)은 무변경.
- assignee 타입에 `user`(개인)도 포함 → SP2b 개인 단위 grant를 모델이 미리 허용. **SP2a 시드는 부서·전직원만.**

#### ② `core/fga/client.py` — `check()` 추가
현재 FGAClient엔 단일 `(user, relation, object)` Check가 없다(ListObjects만). 추가:
```python
async def check(self, user: str, relation: str, object_: str) -> bool:
    # OpenFgaClient.check(ClientCheckRequest(...)) → resp.allowed
```

#### ③ `core/sql/gate.py` — 게이트 로직 교체
`_MATRIX` / `gate_lookup` / `identity_tier` **삭제**. 대체:
```python
RISK_TO_RELATION = {RISK_SELECT: "select", RISK_BULK_SELECT: "bulk_select",
                    RISK_UPDATE_DELETE: "update_delete", RISK_DDL: "ddl"}

async def gate_decision(check, user_id, risk) -> tuple[str, str]:
    suffix = RISK_TO_RELATION.get(risk)
    if suffix is None:
        return DECISION_DENY, f"위험도={risk} 미지원 → DENY"
    user = f"user:{user_id}"
    if await check(user, f"allow_{suffix}", "capability:sql"):
        return DECISION_ALLOW, ...
    if await check(user, f"justify_{suffix}", "capability:sql"):
        return DECISION_JUSTIFY_AND_APPROVE, ...
    return DECISION_DENY, ...
```
- `check`는 `CapabilityChecker` Protocol(`async check(user, relation, object) -> bool`)로 약결합. `gate.py`는 FGAClient를 import하지 않고 순수 정책 유지 → fake로 단위테스트. core·core라 레이어 경계도 깨끗.

#### ④ `app/graph/nodes/tool_gate.py` — 노드 수정
- `user_roles`/`user_departments` 조회는 **감사로그용으로 유지**(department/role 기록 보존).
- `identity_tier`+`gate_lookup` → `await gate_decision(fga_client.check, user_id, risk)`로 교체.

#### ⑤ `scripts/seed_fga.py` — 기본부여 (현행 매트릭스 100% 재현)
| 튜플 | 의미 |
|---|---|
| `user:*` → `allow_select` → `capability:sql` | SELECT 전원 ALLOW |
| `user:*` → `justify_bulk_select` → `capability:sql` | BULK_SELECT 전원 JUSTIFY |
| `department:engineering#member` → `justify_update_delete` → `capability:sql` | UPDATE/DELETE engineering JUSTIFY |
| `role:c_level#member` → `justify_update_delete` → `capability:sql` | UPDATE/DELETE c_level JUSTIFY |
| (DDL 튜플 없음) | DDL 전원 DENY |

기본부여는 고정 정책이므로 `seed_fga.py` 내 상수(`_CAPABILITY_GRANTS`)로 둔다.

## Rationale

- **왜 통일(결정 1)**: 사용자 통찰 — "기본적으로 부여할 수 있는 권한이라는 개념이 있어야 한다. 디렉토리 `can_read`나 SQL `can_XXX`". grant/revoke 도구의 목적 자체가 "권한을 코드가 아니라 데이터로 운영"하는 것인데, SQL 권한이 하드코딩 매트릭스에 있으면 도구가 부여할 대상 관계가 없다. ReBAC 시스템을 쓰면서 권한 절반을 코드에 두는 모순을 제거.
- **왜 명시적 relation(결정 2)**: 권한 종류가 `can_read` + SQL 4종으로 거의 안 바뀐다. 정적인데 굳이 동적 객체로 두면 오타 유령권한·모델 불투명 비용만 진다. relation이면 모델이 곧 문서이고 잘못된 권한명은 Check가 막는다.
- **왜 2층(결정 3)**: OpenFGA Check는 boolean인데 게이트 매트릭스 셀은 3값(ALLOW/JUSTIFY/DENY)이다. `allow_*`/`justify_*` 두 층으로 풀어야 매트릭스를 튜플로 정확히 재현된다. 이러면 게이트 정책이 100% 데이터가 되어 grant 도구로 재배포 없이 운영 가능하고, 미래에 "같은 위험도라도 부서별 ALLOW/JUSTIFY 차등" 같은 셀별 요구도 데이터로 대응된다. 디렉토리 `can_read`는 원래 2-state라 1층 그대로 — 2층이 필요한 건 SQL뿐.
- **왜 분해(SP2a만)**: 모델 통일은 그 자체로 완결되고 "도구 없이도 기존 SQL 경로가 동일 동작(회귀 0)"으로 검증된다. grant 도구(SP2b)는 그 위의 순수 추가라, 검증 경계를 명확히 하려고 분리.

## Consequences

- `core/sql/gate.py`의 매트릭스가 사라지고 게이트 결정이 OpenFGA 튜플로 이동. 게이트 단위테스트(`tests/core/sql/test_gate.py`)는 `gate_decision`을 fake checker로 검증하도록 재작성.
- 게이트 판정이 OpenFGA Check 호출에 의존 → 위험도당 최대 2회 Check. FGA 캐시(PostgreSQL TTL) 적용 여부는 구현 시 검토.
- `identity_tier`/`TIER_*` 상수 제거. 신원 등급 개념은 capability 튜플의 주체(부서·역할 멤버십)로 흡수.
- **SP2b 예고**: grant/revoke 도구는 이 capability 튜플(과 folder dept_viewer)을 조작. "누가 grant할 수 있나"(메타권한)·도구 입력 형식·개인 단위 grant는 SP2b 스펙에서 결정.

## DoD

1. `test_gate.py` 재작성 — fake checker로 `gate_decision`이 각 시드 상황에서 기존과 동일한 ALLOW/JUSTIFY/DENY 반환.
2. `test_tool_gate.py` — mock check 주입으로 노드 분기(ALLOW 실행 / DENY 거부 / JUSTIFY pending) 유지 검증.
3. 통합 — 실제 시드 후 general/engineering/c_level 사용자가 4개 위험도에서 **기존 매트릭스와 동일한 결정**을 받는지.
4. `tests/eval/runner.py` 회귀 점수 확인(하락 시 원인 명시).
5. ADR 인덱스 재생성(`python -m scripts.gen_adr_index`).

## 관련 ADR
- [[ADR-0016]] 신원×위험도 SQL 게이트 (매트릭스 원본 — 이 ADR이 메커니즘 대체)
- [[ADR-0027]] JUSTIFY_AND_APPROVE self-service 게이트 (3-state 의미 유지)
- [[ADR-0015]] FGA public/private/super_reader 폴더 모델 (capability와 공존하는 디렉토리 권한)
- [[ADR-0023]] tool_call 에이전트 루프 (게이트 인터셉터가 capability를 호출)
