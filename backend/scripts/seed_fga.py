"""FGA 시드: users.yaml의 departments → 부서 멤버십, folders.yaml → 폴더 viewer/parent 튜플.

- 부서 멤버십:   user:{uid}            member  department:{d}
- 폴더 viewer:   department:{d}#member viewer  folder:{path}   (viewers 있는 폴더만)
- 폴더 parent:   folder:{parent}       parent  folder:{path}   (path 계층에서 자동 도출)
"""
import asyncio
from pathlib import Path

import asyncpg
import yaml

from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig


def _parent_of(path: str) -> str | None:
    """폴더 path 한 단계 상위. 루트(/company 등)는 None."""
    parts = path.rstrip("/").split("/")
    if len(parts) <= 2:   # ["", "company"] → 루트
        return None
    return "/".join(parts[:-1])


def _build_tuples(users: list[dict], folders: dict) -> list[dict]:
    tuples: list[dict] = []

    # 1) 부서 멤버십
    for user in users:
        uid = user["user_id"]
        for dept in user.get("departments", []):
            tuples.append({
                "user": f"user:{uid}",
                "relation": "member",
                "object": f"department:{dept}",
            })

    # 2) 폴더 viewer + parent
    for path, spec in folders.items():
        spec = spec or {}
        for dept in spec.get("viewers", []):
            tuples.append({
                "user": f"department:{dept}#member",
                "relation": "viewer",
                "object": f"folder:{path}",
            })
        parent = _parent_of(path)
        if parent:
            tuples.append({
                "user": f"folder:{parent}",
                "relation": "parent",
                "object": f"folder:{path}",
            })

    return tuples


async def main() -> None:
    cfg = load_config()
    fga_config = FGAConfig(
        api_url=cfg.fga_api_url,
        store_id=cfg.fga_store_id,
        api_key=cfg.fga_api_key,
        cache_ttl_seconds=cfg.fga_cache_ttl_seconds,
    )

    pool = await asyncpg.create_pool(cfg.postgres_dsn)
    cache = make_cache_backend(cfg.fga_cache_backend, pool)
    client = FGAClient(config=fga_config, cache=cache, pg_pool=pool)

    users = yaml.safe_load(Path("config/users.yaml").read_text())["users"]
    folders = yaml.safe_load(Path("config/folders.yaml").read_text())["folders"]

    tuples = _build_tuples(users, folders)
    # 튜플마다 개별 write — 재실행 시 일부만 존재해도 멱등 처리되도록.
    for t in tuples:
        await client._write_fga_tuples([t])
        print(f"  {t['user']:32} {t['relation']:8} {t['object']}")

    await pool.close()
    print(f"FGA 시드 완료 ({len(tuples)} 튜플)")


if __name__ == "__main__":
    asyncio.run(main())
