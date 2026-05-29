"""config/users.yaml의 teams 필드를 읽어 FGA에 팀 멤버십을 등록한다."""
import asyncio
from pathlib import Path

import asyncpg
import yaml

from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig


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
    for user in users:
        user_id = user["user_id"]
        for team in user.get("teams", []):
            await client.add_team_member(user_id, team)
            print(f"  {user_id} → team:{team}")

    await pool.close()
    print("FGA 시드 완료")


if __name__ == "__main__":
    asyncio.run(main())
