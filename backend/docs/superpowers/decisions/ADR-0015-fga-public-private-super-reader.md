# ADR-0015: FGA 권한 모델 확장 — public/private/dept/super_reader 4축 모델

> **Status**: 🟢 적용완료

**Date**: 2026-06-01
**Context**: ADR-0011의 단순 폴더 트리 모델(`folder.viewer: [department#member]` + `can_read: viewer or can_read from parent`)을, "전체공개가 기본 + private 서브트리 + 명시 부서권한 + 전사 상위 열람권" 정책을 표현하는 모델로 확장. ADR-0011을 supersede.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| ADR-0011 단순 모델 유지 (dept viewer + 상속) | 단순하나 "기본 공개", "특정 서브트리만 비공개", "c_level 전사 열람" 같은 실사용 정책을 표현 못 함 |
| 4축 모델 (dept/public/private/super_reader) | 정책을 1:1로 표현. `but not`(exclusion)·`user:*`(wildcard)·다중 union으로 복잡도 상승, model.json 수동 작성·ListObjects exclusion 검증 필요 |

## Decision

**선택: 4축 모델.** (`fga/model.fga`, `fga/model.json`)

```
type role
  relations
    define member: [user]                                  # c_level 같은 전사 역할
type folder
  relations
    define parent: [folder]
    define dept_viewer: [department#member]
    define dept_access:    dept_viewer   or dept_access from parent
    define public_viewer: [user:*]
    define public_access:  public_viewer or public_access from parent
    define private_flag:  [user:*] or private_flag from parent
    define super_reader:  [role#member] or super_reader from parent
    define can_read: super_reader or dept_access or (public_access but not private_flag)
```

**핵심 결정 2가지**:
1. **`super_reader` 상속(`or super_reader from parent`) 포함**. 미포함 시 `can_read`가 super_reader를 직접 참조하므로 c_level을 루트에 부여해도 하위 폴더가 안 잡혀 전사 열람이 불가능했다. 상속을 넣어 루트 1회 부여로 서브트리 전체를 연다. (dept_access·public_access·private_flag와 상속 대칭 유지)
2. **`dept_access`에는 `but not private_flag`를 걸지 않는다**. private 폴더라도 `dept_viewer`로 명시 부여된 부서원은 본다 — "private 폴더에 명시 권한 복수 부여" 정책과 일치. 공개 권한(public_access)만 private_flag로 차단된다.

**폴더 트리 단일 루트 `/company`**: 코퍼스 루트 디렉토리명을 base_path로 주입(`MarkdownLoader(base_path)`, `build_index`가 `docs/company`→`/company`)하여 모든 폴더를 `/company` 하위로 둔다. public·super_reader를 `/company` 한 곳에만 부여하면 전체 상속. 전사공통 폴더는 코퍼스 루트 디렉토리명과의 혼란을 피해 `company`→`common`으로 rename.

**pre-filter: `prune_to_top_folders` 폐기 + path 정확 매칭(`path = ANY($1)`)으로 전환.** 통합 검증에서 발견한 결함: 옛 `prune`+path-prefix(LIKE) 방식은 "상위 폴더 가시성 = 하위 path 전부 가시"를 전제하는데(ADR-0011의 순수 상속 모델에선 참), `private_flag`로 하위를 선택적으로 차단하는 새 모델에선 이 전제가 깨진다. 모든 사용자가 `/company`(public)를 can_read 하므로 prune이 전원을 `[/company]`로 합치고 `LIKE '/company/%'`가 private(`/company/hr`·`/company/engineering/ops`)까지 노출시켜 권한 경계가 붕괴했다. `ListObjects(can_read)`는 이미 상속을 푼 정확한 가시 폴더 목록을 주므로, prune·prefix 확장 없이 그 목록을 정확 매칭하면 private가 정확히 차단된다.

**현행 데이터 권한 배치** (시드 시연):

| path | 표식 | 열람 |
|------|------|------|
| `/company` | public + super_reader[c_level] | 전 직원 + c_level |
| `/company/common`, `/company/engineering` | (상속) | 전 직원 (public) |
| `/company/engineering/ops` | private + dept_viewers[engineering] | engineering 부서 + c_level |
| `/company/hr` | private + dept_viewers[hr] | hr 부서 + c_level |

`users.yaml`: `all` 부서 제거(public_viewer로 대체), admin은 `fga_roles: [c_level]`, carol은 무소속(public만).

## Rationale

- **모델·인스턴스 직교**: 권한 주체·축이 type 수준으로 정의되어, 부서·폴더·문서를 늘려도 모델은 불변. 데이터 양 증가가 모델 변경 비용을 키우지 않음 ([[project_access_control]], ADR-0014).
- **client 조회 인터페이스 유지, pre-filter만 교체**: `FGAClient`는 여전히 `ListObjects(user, can_read, folder)`만 호출(캐시·permission_node·그 테스트 무영향). 가시 폴더를 검색 필터로 변환하는 단계만 prune+prefix → 정확 매칭(`build_pg_filter`)으로 교체했다.
- **검증**: `seed_fga._build_tuples`·`MarkdownLoader.base_path`·`build_pg_filter` 정확 매칭을 TDD로 작성, 전체 단위테스트 318 통과. 로컬 OpenFGA 통합 검증으로 alice/bob/carol/admin 권한 매트릭스가 의도대로 동작함을 확인(private 차단·super_reader 관통). 코퍼스 내용 불변(rename·path prefix만)이라 eval 검색 품질 회귀는 없음.

## 미해결 / 후속 검증 (실 통합 시)

- **ListObjects + `but not`**: 로컬 OpenFGA 통합 검증 완료 — `can_read`의 exclusion(`public_access but not private_flag`)이 ListObjects에서 정확히 동작(carol이 private 제외). 고부하 성능 특성은 운영 규모에서 재확인 권장.
- **private 영구성**: `private_flag from parent`가 무조건 상속되어 private 서브트리 내 하위 폴더를 다시 공개로 전환 불가(현 정책상 의도).
- **인덱스**: `path = ANY($1)` 정확 매칭은 일반 btree(`path`) 인덱스가 최적. 기존 `text_pattern_ops` 인덱스(LIKE prefix용)는 equality도 처리하나, 운영 시 일반 btree로 정리 검토(NFR-3).
- **실 적용 절차**: `scripts/fga_init.sh`(새 model.json 등록) → `scripts/seed_fga.py` → `scripts/build_index.py`(재인덱싱) 순. 데이터 양 확장은 ADR-0014 별도 작업.

## 영향받는 결정

- **ADR-0011** — superseded. dept viewer 단일 축 모델을 4축 모델로 대체.
- **ADR-0014** — 본 모델 확정 후 시드 데이터 전면 재구성을 진행할 수 있음(보류 해제 전제).

> **후속(ADR-0051)**: `dept_viewer: [department#member]`는 `viewer: holder from gated_by`(permission 경유 TTU)로 전환, `dept_access`는 `access`로 개명됨. pre-filter 메커니즘(`ListObjects(can_read)` → 정확 매칭)은 불변.
