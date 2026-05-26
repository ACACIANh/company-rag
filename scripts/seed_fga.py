"""config/users.yaml의 teams 필드를 읽어 FGA에 팀 멤버십을 등록한다."""
from pathlib import Path

import yaml

from shared.config import load_config
from shared.fga.cache import make_cache_backend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig


def main() -> None:
    cfg = load_config()
    fga_config = FGAConfig(
        api_url=cfg.fga_api_url,
        store_id=cfg.fga_store_id,
        api_key=cfg.fga_api_key,
        pg_dsn=cfg.postgres_dsn,
    )
    client = FGAClient(config=fga_config, cache=make_cache_backend(cfg.fga_cache_backend, cfg.postgres_dsn))

    users = yaml.safe_load(Path("config/users.yaml").read_text())["users"]
    for user in users:
        user_id = user["user_id"]
        for team in user.get("teams", []):
            client.add_team_member(user_id, team)
            print(f"  {user_id} → team:{team}")

    print("FGA 시드 완료")


if __name__ == "__main__":
    main()
