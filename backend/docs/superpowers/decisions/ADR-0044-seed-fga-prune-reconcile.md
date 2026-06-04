# ADR-0044: seed_fga --prune — 추가식 시드의 잔재 정리(재조정)

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-04
**Context**: `scripts.seed_fga`는 멱등·추가식이라 부서·사용자 개명 시 옛 튜플(`department:hr`, `user:user-alice` 등)이 라이브 store에 잔존한다. config와 store를 정합화하는 `--prune` 옵션을 추가한다.

## 배경
부서명 정리(`hr`→`인사팀`, ADR-0043 후속) 후 라이브 FGA store에 옛 `department:hr` 멤버십·viewer와, capability 매트릭스 정리로 모델에서 제거된 relation을 가리키는 고아 튜플(`allow_update_delete`)이 남았다. 시드를 다시 돌려도 추가만 되고 삭제는 안 돼 drift가 누적된다. 이번엔 일회성 스크립트로 정리했지만, 개명·정리 때마다 반복되는 문제다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. 매번 수동/일회성 스크립트 | 코드 부채 없음. 그러나 반복 작업·실수 위험·재현 불가 |
| B. store 재생성(wipe & recreate) | 가장 깨끗하나 store_id 변경 → `.env` 수정·앱 재기동 필요. 런타임에 정당히 추가된 튜플도 소실 |
| **C. seed_fga --prune (재조정)** | 라이브를 전수 읽어 config(`_build_tuples`)와의 차집합만 삭제. store_id 불변, 추가(write)는 기존 멱등 경로 유지. 단일 출처(seed)에 정합 로직 편입 |

## Decision
**선택: C — `python -m scripts.seed_fga --prune`**

- `FGAClient.list_all_tuples()`: store 전수 읽기(OpenFGA Read API 페이지네이션).
- `seed_fga._prune(client, desired)`: `live - desired_keys`(stale)만 `revoke_tuple`로 삭제, 삭제 목록 반환.
- `main(prune)`: **write(추가) → prune(삭제)** 순서로 결과적으로 `라이브 store == config`.
- 무옵션 기본 동작(추가식 멱등 시드)은 그대로 보존.

## Rationale
- **단일 출처 정합**: 삭제 기준이 코드 분기가 아니라 `_build_tuples(config)` — 시드의 desired와 동일. 정의가 한 곳.
- **비파괴적**: store_id 불변(`.env`·앱 무영향), 전체 wipe 아님.
- ⚠️ **source-of-truth와의 긴장(중요)**: 멤버십의 source of truth는 OpenFGA이고 `config/users.yaml`은 부트스트랩 시드 입력일 뿐이다(CLAUDE.md 아키텍처 결정). 따라서 `--prune`는 "config로 store를 **되돌리는**" 부트스트랩 정합화 도구이지 일상 운영 도구가 아니다. 운영 중 `manage_permission`·관리자 API로 정당히 부여된 튜플은 config에 없으므로 `--prune`가 **삭제**한다. 그래서 무옵션 시드는 추가식(비파괴)으로 두고, `--prune`는 개명·리셋 같은 의도적 재정합 때만 명시 옵트인으로 쓴다.
- **테스트 가능**: 차집합·삭제 디스패치(`_prune`)와 페이지네이션(`list_all_tuples`)을 클라이언트 mock으로 단위 테스트. 라이브 의존 없음.

## 변경 파일
- `core/fga/client.py`: `list_all_tuples()` 추가
- `scripts/seed_fga.py`: `_prune()` + `--prune` argparse, 모듈 docstring 갱신
- `tests/scripts/test_seed_fga.py`: `_prune` stale-only/no-op 테스트
- `tests/core/fga/test_client.py`: `list_all_tuples` 페이지네이션 테스트

## 검증
전체 521 passed. 라이브 실행 `python -m scripts.seed_fga --prune` → "39 튜플, prune 0 삭제"(이미 정합 상태) 확인.
