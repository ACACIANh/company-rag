# ADR-0012: 문서 인덱스 동기화 — 버전 스냅샷 + 최신 프로젝션

> **Status**: 🟢 적용완료 (대폭 축소) — 아래 결정사항 중 실제 코드에 남은 것은 **"pgvector 단일 투영(최신 청크만)"** 개념뿐. `document_versions` 이력 레이어·`PostgresDocumentVersionStore`·버전 보존 정책·스케줄러·`content_hash` 변경 감지·`delete_by_document`·원자적 스왑·`/admin/index/sync`는 **모두 미구현/폐기**. 현재 구현: `POST /admin/index/rebuild`(전체 재구성)만 존재. 아래 Decision 섹션은 원래 설계의 역사 기록이며 현행 코드를 반영하지 않는다.

- 상태: 채택(Accepted)
- 날짜: 2026-06-01
- 관련: 역기획서 §6(NFR-2 권한 캐시 TTL), §7.6(인제스천), §9.3(캐시 무효화)

---

## Context (배경 / 왜 만드는가)

현행 인덱스는 `POST /admin/index/rebuild`로 **전체를 지우고 다시 쌓는** 방식뿐이다.
문서의 추가·수정·삭제를 반영하려면 매번 전량 재구성해야 하고, 변경 이력도 남지 않는다.

문서 변경을 인덱스에 반영하는 방법을 정해야 했고, 다음을 고려했다.

**실시간 반영을 하지 않기로 한 이유**
- 임베딩은 느리고 비싸다. 업로드 요청의 임계경로에 끼우면 지연·부분실패가 생긴다.
- 인제스천은 다단계 파이프라인(스캔 → 변경 감지 → 청킹 → 임베딩 → 반영)이라
  재시도·멱등성을 다루기엔 백그라운드 잡이 적합하다.
- 권한 캐시(NFR-2)가 이미 60s TTL로 staleness를 허용한다.
  검색만 실시간을 강제하면 시스템 전체의 일관성 철학이 어긋난다 → "수 분 지연 허용"으로 통일.
- 사내 지식베이스는 초 단위로 바뀌지 않아 staleness 비용이 사실상 0이다.

**vector store에 최신 버전만 두기로 한 이유**
- 버전을 vector store에 모두 쌓으면 매 쿼리에 `is_current` 류 필터가 붙고,
  HNSW 그래프에 구버전(죽은 벡터)이 섞여 탐색 경로·recall이 함께 나빠진다.
- 최신만 두면 인덱스가 항상 최소 크기 → 검색 속도·품질 유지.
- 이력은 텍스트라 따로 보관해도 저장비용이 사실상 0이며, **쿼리 타임엔 절대 건드리지 않는다.**

---

## Decision (결정사항)

읽기/쓰기 모델을 분리한다(CQRS / 읽기모델 프로젝션).

| 레이어 | 저장소 | 내용 |
|--------|--------|------|
| 이력 (source of truth) | Postgres `document_versions` | 문서 버전 스냅샷(텍스트만) |
| 서빙 (projection) | pgvector | 최신 버전 청크만 |

1. **이력은 텍스트만 저장**(임베딩 X). 롤백 시 재임베딩한다.
   - 임베딩까지 쌓으면 저장 폭증 + 임베더 교체 시(NFR-9) 옛 벡터가 무용지물.
2. **버전 판별은 `version` 최대값**으로 파생한다. `is_current` 플래그를 두지 않는다.
   - 상태 동기화 부담·정합성 버그 원천 제거(단일 진실).
3. **삭제는 `deleted_at` soft delete**. NULL = 라이브, 값 = 삭제 시점.
4. **변경 감지는 `content_hash`**(본문 SHA-256). 저장된 해시와 대조해 안 바뀐 문서는 재임베딩 스킵.
   - Flyway의 마이그레이션 checksum과 같은 원리(내용 지문으로 변경 감지).
     단, Flyway는 변경을 에러로 막지만 여기선 새 버전으로 누적한다.
5. **정기 재인제스천 잡**: 소스 스캔 → hash 비교로 변경분만 → 새 버전 기록 →
   재청킹·재임베딩 → **트랜잭션 내에서 구청크 delete + 신청크 add(원자적 스왑)**.
6. **트리거는 수동**(`POST /admin/index/sync`). 스케줄러는 향후 확장.
   기존 `rebuild`(전체 재구성)는 그대로 유지.

### VectorStore 인터페이스 변경
기존 `add / search / count`에 하나만 추가.
```python
class VectorStore(ABC):
    @abstractmethod
    def delete_by_document(self, document_id: str) -> None: ...
```
`Chunk`에 `document_id`(path 기반 안정 키) 필드 추가.

---

## Consequences (영향)

**+ 좋아지는 점**
- vector store 항상 최소 크기 → 검색 속도·recall 유지.
- 버전 이력이 곧 **문서 변경 감사 로그**로 재활용된다(audit 테마와 연결).
  "어떤 문서가 언제 어느 버전으로 바뀌었나, 지금 라이브는 몇 버전"을 그대로 답한다.
- 트리거 레이어만 단순하고, 멱등 처리(upsert/delete) 메커니즘은 견고하게 유지.

**− 감수하는 점**
- 반영은 잡 실행 시점까지 지연(수 분, 허용 범위).
- 롤백은 즉시가 아니라 해당 버전 재임베딩 1회를 거친다.
- "전체 라이브 문서 목록"은 `document_id`별 `MAX(version)` group by가 필요(동기화 잡에서만 사용, 쿼리 타임 무관).

**폐기된 설계 (2026-06-04)**
- ~~`document_versions` 이력 테이블 (Postgres)~~ — 스키마만 생성됐고 실제 read/write 구현 없이 방치됨. 포트폴리오 범위에서 불필요로 판단하여 `core/document_version/` 모듈·테스트·`chat.py` lifespan 호출 전체 삭제. 기존에 `ensure_table()`로 생성된 테이블은 `DROP TABLE IF EXISTS document_versions;`로 수동 정리 필요.
- ~~버전 보존 정책(최근 N개 / N일)~~ — 이력 레이어 폐기로 불필요.
- ~~스케줄러(주기 트리거)~~ — 포트폴리오 범위 제외.
