import hashlib

import asyncpg

from core.document_original.base import DocumentOriginalStore, OriginalRecord


class PostgresDocumentOriginalStore(DocumentOriginalStore):
    """document_originals 테이블 구현. content_hash로 변경 감지·버전 관리."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_originals (
                    document_id   TEXT        NOT NULL,
                    version       INT         NOT NULL,
                    folder_path   TEXT        NOT NULL,
                    filename      TEXT        NOT NULL,
                    mime          TEXT        NOT NULL,
                    original_file BYTEA       NOT NULL,
                    content_hash  TEXT        NOT NULL,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (document_id, version)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_originals_folder "
                "ON document_originals (folder_path text_pattern_ops)"
            )

    async def save(
        self, document_id: str, folder_path: str, filename: str, mime: str, raw: bytes
    ) -> None:
        content_hash = hashlib.sha256(raw).hexdigest()
        async with self._pool.acquire() as conn:
            latest = await conn.fetchrow(
                "SELECT version, content_hash FROM document_originals "
                "WHERE document_id = $1 ORDER BY version DESC LIMIT 1",
                document_id,
            )
            if latest is not None and latest["content_hash"] == content_hash:
                return  # 동일 원본 → 재저장 skip
            next_version = (latest["version"] + 1) if latest is not None else 1
            await conn.execute(
                "INSERT INTO document_originals "
                "(document_id, version, folder_path, filename, mime, original_file, content_hash) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                document_id, next_version, folder_path, filename, mime, raw, content_hash,
            )

    async def get_latest(self, document_id: str) -> OriginalRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT document_id, version, folder_path, filename, mime, "
                "original_file, content_hash FROM document_originals "
                "WHERE document_id = $1 ORDER BY version DESC LIMIT 1",
                document_id,
            )
        if row is None:
            return None
        return OriginalRecord(
            document_id=row["document_id"],
            version=row["version"],
            folder_path=row["folder_path"],
            filename=row["filename"],
            mime=row["mime"],
            original_file=row["original_file"],
            content_hash=row["content_hash"],
        )
