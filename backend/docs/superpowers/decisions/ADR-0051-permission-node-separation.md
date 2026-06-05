# ADR-0051: permission 1급 노드 분리 — 권한↔부서 분리

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: 권한 부여가 부서 멤버십 부여와 강제로 결합돼 있어, "개인에게 특정 폴더 하나만" 주려면 부서 전체에 가입시켜야 했다(최소권한 위반). `type permission` 1급 노드를 도입해 권한을 부서 멤버십에서 분리한다.

Spec: [`docs/superpowers/specs/2026-06-05-permission-department-separation-design.md`](../specs/2026-06-05-permission-department-separation-design.md)

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| A. 부서 완전 분리 (folder/table type 통합) | folder·table을 단일 type으로 물리 통합. folder 고유 구조(트리상속·private)를 table이 떠안아 모델 오염. 과추상화 → 기각 |
| B. `access_group` 신설 (별도 그룹 개체) | 새 관리 차원 도입. 부서·그룹 이중 관리 부담. YAGNI → 기각 |
| C. `permission` 1급 노드 경유 (TTU) | 폴더·테이블을 통합하지 않고 추상 레이어만 추가. 검색/실행 코드 불변. holder 한 줄로 부서·개인·역할을 동시 지원. **채택** |

## Decision

**선택: C — `type permission` 경유 TTU(Tuple-to-Userset) 모델**

### FGA 모델 변경

신설 type:
```
type permission
  relations
    define holder: [user, user:*, department#member, role#member]
```

folder — `dept_viewer`/`dept_access` → `viewer`/`access` 개명 + permission 경유 TTU:
```
type folder
  relations
    define parent: [folder]
    define gated_by: [permission]
    define viewer:  holder from gated_by          # (구 dept_viewer)
    define access:  viewer or access from parent  # (구 dept_access)
    define public_viewer: [user:*]
    define public_access: public_viewer or public_access from parent
    define private_flag:  [user:*] or private_flag from parent
    define super_reader:  [role#member] or super_reader from parent
    define can_read: super_reader or access or (public_access but not private_flag)
```

table — 동형 전환:
```
type table
  relations
    define gated_by: [permission]
    define viewer:   holder from gated_by         # (구 dept_viewer)
```

capability — permission#holder 경유로 통일(`justify_grant` 예외):
```
type capability
  relations
    define allow_select:          [permission#holder]
    define justify_select:        [permission#holder]
    define justify_bulk_select:   [permission#holder]
    define justify_update_delete: [permission#holder]
    define justify_ddl:           [permission#holder]
    define justify_grant:         [user, department#member, role#member]  # 메타권한 유지
```

### 위임 정책 (ADR-0046 대체)

| 행위 | c_level | 부서 팀장(dept admin) |
|------|---------|----------------------|
| **정의** `permission gated_by resource` / capability 연결 | ✅ | ❌ — 부서 경계 누수 차단 |
| **배정** `user holder permission:X` (개인 부여) | ✅ 전체 | ✅ 자기 부서가 holder인 permission 한정 |
| 부서 멤버십 `user member department` | ✅ | ✅ 자기 부서 (기존 유지) |

게이트(`tool_gate_node`): planned_action이 `grant <user> holder permission:X`이고 요청자가 X를 보유한 부서의 admin이면 `DENY → JUSTIFY_AND_APPROVE` 승격.

### 부서 id 정규화

`인사팀 → 인사` 등 6개 부서명에서 "팀" 제거 — permission 이름과 business DB 부서 데이터를 완전 통일.

### 마이그레이션

Big bang: 기존 `dept_viewer: [department#member]` 직접연결 → permission 전면 전환. `seed_fga.py --prune`으로 stale 튜플 정리 후 재시드.

## Rationale

- **검색/실행 코드 불변**: `ListObjects(user, can_read, folder)` 호출 시그니처는 변하지 않는다. FGA가 `user → permission#holder → gated_by → folder` 체인을 내부에서 해소하므로 `retrieve.py`·`gate.py`·`client.py`는 손대지 않는다.
- **permission이 추상 레이어**: folder·table을 물리 통합하지 않고도 이질적 리소스를 "권한 묶음" 단위로 연결한다. folder 고유 구조(트리 상속·private·public)는 그대로 보존.
- **private 보장 직교 유지**: `private_flag`·`super_reader`는 permission과 무관하게 유지된다. permission holder가 있어도 private 폴더 상속이 public으로 새지 않는다.
- **부서명 = permission 이름 통일**: `permission:인사` = `department:인사` — OpenFGA 권한과 business DB 데이터가 같은 id를 쓰므로 매핑 테이블이 불필요.
- **holder 한 줄 다양성**: `[user, user:*, department#member, role#member]` 한 줄로 개인·전직원·부서·역할 경로를 동시 지원하면서 인터페이스가 단일화된다.

## 대안 기각 이유

- **폴더/table 물리 통합**: table이 `parent`·`private_flag`를 떠안아 쓰지 않는 relation이 생겨 누수 표면 증가. `permission` 노드가 이미 추상화 레이어이므로 resource를 또 합칠 실익 없음.
- **access_group 신설**: 부서·그룹 이중 관리, 기존 department 개념과 중복. 현 범위에서 YAGNI.

## 영향

- **ADR-0046** — 🟣 대체됨. 위임 단위가 "부서 멤버십만"에서 "정의(c_level)/배정(c_level+팀장)" 분리로 재설계.
- **ADR-0015** — 개정. folder `dept_viewer: [department#member]` → `viewer: holder from gated_by`. pre-filter 메커니즘 불변.
- **ADR-0050** — 개정. table도 `viewer: holder from gated_by` 통일. 기존 "개인 직접 부여 불가" 진술을 permission 배정으로 대체.
- **ADR-0033** — `dept_viewer`/`dept_access` → `viewer`/`access` 개명의 명명 근거.

## 검증

- smoke 6/6 통과 (6개 핵심 시나리오)
- 610 테스트 통과 (회귀 없음)
- 주요 단위 테스트: `permission_validator`(개인 배정 허용·팀장 경계 외 정의 거부), 위임 승격(자기 부서 permission 개인 배정 JUSTIFY·타 부서 DENY), big bang 재시드 후 기존 부서원 접근 동등성 유지
