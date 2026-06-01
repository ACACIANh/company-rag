import asyncpg


class PostgresDocumentVersionStore:
    """문서 버전 이력 저장소(source of truth).

    서빙 모델(pgvector `documents`)은 최신 버전만 투영(projection)한다. ADR-0012 참조.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    document_id  TEXT        NOT NULL,           -- path 기반 안정 키 (예: '/eng/onboarding.md')
                    version      INT         NOT NULL,           -- 1부터 증가. 최대값 = 최신 버전
                    content      TEXT        NOT NULL,           -- 문서 본문 텍스트만 저장 (임베딩 X)
                    content_hash TEXT        NOT NULL,           -- 본문 SHA-256. 변경 감지용 (Flyway checksum과 동일 원리)
                    deleted_at   TIMESTAMPTZ,                    -- NULL = 라이브, 값 = 삭제 시점 (soft delete)
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (document_id, version)
                )
            """)
            # 살아있는 문서의 최신 버전은 (document_id, version) PK의 prefix scan으로 조회한다
            # (WHERE document_id = $1 ORDER BY version DESC LIMIT 1). PK가 이를 커버하므로
            # 별도 인덱스는 두지 않는다. 단순함 유지.
