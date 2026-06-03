"""FGA 시드: users.yaml → 멤버십, folders.yaml → 폴더 권한/parent 튜플.

- 부서 멤버십:   user:{uid}            member         department:{d}   (departments)
- 역할 멤버십:   user:{uid}            member         role:{r}         (fga_roles)
- 전체공개:      user:*                public_viewer  folder:{path}    (public: true)
- private 표식:  user:*                private_flag   folder:{path}    (private: true)
- 부서 명시권한: department:{d}#member dept_viewer    folder:{path}    (dept_viewers)
- 전사 열람권:   role:{r}#member       super_reader   folder:{path}    (super_readers)
- 폴더 parent:   folder:{parent}       parent         folder:{path}    (path 계층에서 자동 도출)
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


# capability:sql 기본부여(ADR-0028) — 현행 게이트 매트릭스를 튜플로 재현.
# SELECT 전원 ALLOW / BULK_SELECT 전원 JUSTIFY / UPDATE_DELETE engineering·c_level JUSTIFY / DDL 전원 DENY(튜플 없음).
_CAPABILITY_GRANTS = [
    {"user": "user:*", "relation": "allow_select", "object": "capability:sql"},
    {"user": "user:*", "relation": "justify_bulk_select", "object": "capability:sql"},
    {"user": "department:engineering#member", "relation": "justify_update_delete", "object": "capability:sql"},
    {"user": "role:c_level#member", "relation": "justify_update_delete", "object": "capability:sql"},
]


def _build_tuples(users: list[dict], folders: dict) -> list[dict]:
    tuples: list[dict] = []

    # 1) 부서 멤버십 + 역할 멤버십
    for user in users:
        uid = user["user_id"]
        for dept in user.get("departments", []):
            tuples.append({
                "user": f"user:{uid}",
                "relation": "member",
                "object": f"department:{dept}",
            })
        for role in user.get("fga_roles", []):
            tuples.append({
                "user": f"user:{uid}",
                "relation": "member",
                "object": f"role:{role}",
            })

    # 2) 폴더 권한 + parent
    for path, spec in folders.items():
        spec = spec or {}
        if spec.get("public"):
            tuples.append({
                "user": "user:*",
                "relation": "public_viewer",
                "object": f"folder:{path}",
            })
        if spec.get("private"):
            tuples.append({
                "user": "user:*",
                "relation": "private_flag",
                "object": f"folder:{path}",
            })
        for dept in spec.get("dept_viewers", []):
            tuples.append({
                "user": f"department:{dept}#member",
                "relation": "dept_viewer",
                "object": f"folder:{path}",
            })
        for role in spec.get("super_readers", []):
            tuples.append({
                "user": f"role:{role}#member",
                "relation": "super_reader",
                "object": f"folder:{path}",
            })
        parent = _parent_of(path)
        if parent:
            tuples.append({
                "user": f"folder:{parent}",
                "relation": "parent",
                "object": f"folder:{path}",
            })

    # 3) capability 기본부여(ADR-0028)
    tuples.extend(_CAPABILITY_GRANTS)

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
