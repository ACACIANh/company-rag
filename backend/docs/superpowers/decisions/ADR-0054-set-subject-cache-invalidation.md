# ADR-0054: 집합 subject 권한 변경 시 폴더 캐시 무효화 (TTU 파급)

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: `FGAClient.grant_tuple`/`revoke_tuple`이 변경 주체(subject)의 캐시만 무효화했다(`_cache_key_for(subject)`). 그러나 운영 권한 모델(`config/permissions.yaml`)은 `department:D#member`를 permission holder로 쓰는 게 표준이라, `permission`을 부서에 grant/revoke하면 TTU(tuple-to-userset)로 **그 부서 멤버 전원**의 실효 폴더 권한이 바뀐다. 멤버들의 폴더 캐시(`get_readable_folders`, bare user id 키)는 무효화되지 않아, **revoke된 폴더가 캐시 TTL(기본 60초)까지 RAG pre-filter에 계속 노출**됐다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| A. department#member만 멤버 열거 무효화 / role#member는 no-op | 비용 최소처럼 보이나, `role:R#member`는 super_reader(`model.fga`)로 폴더 can_read 경로가 있어 no-op이면 `seed_fga --prune`의 super_reader revoke가 누수. **기각(전제 오류)** |
| B. 모든 `X#member` userset(department·role 등)을 멤버 열거해 개별 무효화 + 열거/무효화 실패 시 캐시 전체 flush(fail-closed) | 폴더 권한 경유 종류(holder·super_reader) 불문 누수 차단. 부분 실패 fail-open까지 차단. `core/fga/` 한정. **채택** |
| C. TTL 단축 미봉책 | 누수 윈도우만 줄일 뿐 근본 해결 못 함. **기각** |

## Decision

**선택: B — 모든 `X#member` userset 멤버 열거 무효화 + fail-closed 폴백**

### 구현 세부

**`core/fga/client.py`** — `_invalidate_subject_cache(subject)` 디스패처 신설, `grant_tuple`/`revoke_tuple`이 `_cache.invalidate(_cache_key_for(subject))` 대신 이를 호출:
```python
async def _invalidate_subject_cache(self, subject):
    if subject.endswith("#member"):                 # department:D#member / role:R#member
        userset_object = subject[:-len("#member")]
        try:
            for member_id in await self._list_userset_member_ids(userset_object):
                await self._cache.invalidate(member_id)   # bare user id로 키잉
        except Exception:
            await self._cache.clear_all()           # 열거/무효화 실패 → fail-closed 전체 flush
        return
    await self._cache.invalidate(self._cache_key_for(subject))  # 개별 user / 그 외
```

**`_list_userset_member_ids(userset_object)`** — OpenFGA `Read(object=userset_object, relation=member)`로 멤버 user id(bare) 페이지네이션 조회.

**`PermissionCacheBackend.clear_all()`** — ABC + `InMemoryCacheBackend`/`PostgresCacheBackend` 구현 추가(전체 비우기).

## Rationale

- **개별 user grant는 본인만 영향**: `user:X holder permission:Y`면 X 캐시만 비우면 충분 — 기존 동작 유지.
- **집합 grant/revoke는 파급(종류 불문)**: `department:D#member holder permission:Y`(holder 경유)와 `role:R#member super_reader folder:Z`(super_reader 경유, `model.fga`) 모두 멤버 전원의 가시 폴더를 바꾼다. ADR-0002의 "권한 변경 이벤트(write 후 flush)" 원칙상 멤버 전원 flush가 요구된다.
- **role#member도 폴더 경유가 있다**: 초기 설계는 "전사 permission은 table 전용이라 role#member는 폴더 캐시 무관"이라 봤으나 **오류였다** — `role:c_level#member`는 `super_reader folder:/company`를 쥐므로(`scripts/seed_fga.py`) `seed_fga --prune`이 그 super_reader 튜플을 revoke하면 멤버 캐시 누수가 발생한다. 따라서 department/role을 가르지 않고 `X#member` 일반으로 처리한다.
- **fail-closed 폴백**: revoke는 FGA delete가 먼저 커밋된 뒤 캐시를 비운다. 멤버 열거(Read)나 개별 무효화가 transient 실패하면 회수 폴더가 TTL까지 노출되는 fail-open이 된다. 멤버 목록 없이는 타깃 무효화가 불가하므로, 실패 시 캐시 전체를 flush해 fail-closed로 만든다(전수 재조회 비용 < 권한 누수). grant 측은 stale=under-permission이라 무해.

## 영향

- **성능**: `X#member` grant/revoke당 FGA Read 1회(멤버 열거) 추가. department·role 규모가 작아(현 ≤수십 명) 무시 가능. 폴백 flush는 드문 실패 경로에서만.
- **레이어**: `core/fga/` 한정. LangGraph 미import, ABC에 `clear_all` 추가(구현체 2개 모두 반영), 미연결 추상화 삭제 없음.
- **차단 경로 무영향**: 부서 팀장의 집합 grant 위임은 `delegated_permission`이 user subject만 허용해 차단됨(변경 없음). 본 무효화는 c_level의 집합 grant/revoke 및 `seed_fga --prune` 경로에서 발동.

## 관련

- [ADR-0051](ADR-0051-permission-node-separation.md) — permission 노드 통일(부서·개인 holder). 집합 holder 파급의 발원
- [ADR-0002](ADR-0002-fga-cache-strategy.md) — FGA 캐시 전략(write 후 flush 원칙)
- [ADR-0015](ADR-0015-fga-public-private-super-reader.md) — 폴더 트리 pre-filter(캐시된 allowed_folders 소비처)
