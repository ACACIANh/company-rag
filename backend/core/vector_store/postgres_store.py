import json

import asyncpg

from core.models import Chunk, SearchResult
from core.vector_store.base import VectorStore


class PostgresVectorStore(VectorStore):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    chunk_id    TEXT        UNIQUE NOT NULL,
                    content     TEXT        NOT NULL,
                    embedding   vector(1536),
                    metadata    TEXT        NOT NULL DEFAULT '{}',
                    path        TEXT        NOT NULL DEFAULT '',
                    source      TEXT        NOT NULL DEFAULT '',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_hnsw "
                "ON documents USING hnsw (embedding vector_cosine_ops)"
            )
            # path prefix(LIKE '/x/%')·등호 매칭용. text_pattern_ops로 anchored LIKE 인덱스 활용.
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_path "
                "ON documents (path text_pattern_ops)"
            )

    async def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None:
        rows = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            meta = extra_metadata[i] if extra_metadata and i < len(extra_metadata) else {}
            rows.append((
                chunk.chunk_id,
                chunk.text,
                emb,
                json.dumps({**chunk.metadata, "source": chunk.source, **meta}),
                chunk.metadata.get("path", ""),
                chunk.source,
            ))
        async with self._pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO documents
                    (chunk_id, content, embedding, metadata, path, source)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    path = EXCLUDED.path,
                    source = EXCLUDED.source
            """, rows)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        params = params or []
        emb_param_idx = len(params) + 1
        limit_param_idx = emb_param_idx + 1
        where_sql = f"AND ({where_clause})" if where_clause else ""
        sql = f"""
            SELECT chunk_id, content, source, metadata,
                   1 - (embedding <=> ${emb_param_idx}) AS score
            FROM documents
            WHERE embedding IS NOT NULL {where_sql}
            ORDER BY embedding <=> ${emb_param_idx}
            LIMIT ${limit_param_idx}
        """
        all_params = params + [query_embedding, top_k]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *all_params)
        output = []
        for row in rows:
            meta = json.loads(row["metadata"])
            chunk = Chunk(
                text=row["content"],
                source=row["source"],
                chunk_id=row["chunk_id"],
                metadata=meta,
            )
            output.append(SearchResult(chunk=chunk, score=float(row["score"])))
        return output

    async def count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM documents")
