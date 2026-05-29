"""vector(384) → vector(1536) 마이그레이션 스크립트.

기존 documents 테이블의 embedding 컬럼을 vector(1536)으로 변경하고
모든 행을 text-embedding-3-small로 재임베딩한다.

사용법:
    python -m scripts.migrate_embeddings_1536 [--dry-run] [--batch-size N]

옵션:
    --dry-run     SQL 변경 없이 영향 범위만 출력
    --batch-size  한 번에 처리할 행 수 (기본값: 100)
"""

import argparse
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import asyncpg
from pgvector.asyncpg import register_vector

from shared.config import load_config
from shared.embedder.openai_embedder import OpenAIEmbedder


async def _alter_column(conn: asyncpg.Connection, dry_run: bool) -> None:
    """embedding 컬럼 타입을 vector(1536)으로 변경한다."""
    row = await conn.fetchrow(
        """
        SELECT atttypmod
        FROM pg_attribute
        JOIN pg_class ON pg_class.oid = pg_attribute.attrelid
        WHERE pg_class.relname = 'documents'
          AND pg_attribute.attname = 'embedding'
          AND NOT pg_attribute.attisdropped
        """
    )
    if row is None:
        print("[skip] documents 테이블 또는 embedding 컬럼이 없습니다.")
        return

    # pgvector는 atttypmod에 차원 수를 저장한다 (0-indexed offset 없음, 값 그대로)
    current_dim = row["atttypmod"]
    if current_dim == 1536:
        print(f"[skip] 이미 vector(1536)입니다.")
        return

    print(f"[alter] embedding 컬럼 타입 변경: vector({current_dim}) → vector(1536)")
    if not dry_run:
        # 기존 벡터와 인덱스를 제거한 뒤 컬럼 타입 변경
        await conn.execute("DROP INDEX IF EXISTS idx_documents_hnsw")
        await conn.execute("UPDATE documents SET embedding = NULL")
        await conn.execute(
            "ALTER TABLE documents ALTER COLUMN embedding TYPE vector(1536)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_hnsw "
            "ON documents USING hnsw (embedding vector_cosine_ops)"
        )
        print("[alter] 완료")


async def _reembed_batch(
    conn: asyncpg.Connection,
    embedder: OpenAIEmbedder,
    batch_size: int,
    dry_run: bool,
) -> int:
    """NULL이거나 차원이 다른 행을 배치 단위로 재임베딩한다."""
    offset = 0
    total_updated = 0

    while True:
        rows = await conn.fetch(
            "SELECT id, content FROM documents ORDER BY created_at LIMIT $1 OFFSET $2",
            batch_size,
            offset,
        )
        if not rows:
            break

        texts = [r["content"] for r in rows]
        ids = [r["id"] for r in rows]

        print(f"  배치 offset={offset}, rows={len(rows)} → 임베딩 요청 중...")
        if not dry_run:
            embeddings = embedder.embed_batch(texts)
            await conn.executemany(
                "UPDATE documents SET embedding = $1 WHERE id = $2",
                list(zip(embeddings, ids)),
            )

        total_updated += len(rows)
        offset += batch_size

    return total_updated


async def run(dry_run: bool, batch_size: int) -> None:
    config = load_config()

    if not config.postgres_dsn:
        print("[error] POSTGRES_DSN 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    if not config.openai_api_key:
        print("[error] OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    embedder = OpenAIEmbedder(
        model_name=config.embedding_model,
        api_key=config.openai_api_key,
    )

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn)
    try:
        async with pool.acquire() as conn:
            total_rows = await conn.fetchval("SELECT COUNT(*) FROM documents")
            print(f"[info] 총 {total_rows}개 행 처리 예정 (batch_size={batch_size})")

            if dry_run:
                print("[dry-run] 실제 변경 없이 검사만 수행합니다.")

            await _alter_column(conn, dry_run)
            updated = await _reembed_batch(conn, embedder, batch_size, dry_run)
            print(f"\n[done] {'(dry-run) ' if dry_run else ''}{updated}개 행 재임베딩 완료")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 검사만 수행")
    parser.add_argument("--batch-size", type=int, default=100, metavar="N")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
