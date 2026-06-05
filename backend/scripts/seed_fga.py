"""FGA 시드: users.yaml → 멤버십, folders.yaml → 폴더 권한/parent, permissions.yaml → permission 튜플.

- 부서 멤버십:      user:{uid}            member         department:{d}   (departments)
- 역할 멤버십:      user:{uid}            member         role:{r}         (fga_roles)
- 전체공개:         user:*                public_viewer  folder:{path}    (public: true)
- private 표식:     user:*                private_flag   folder:{path}    (private: true)
- 전사 열람권:      role:{r}#member       super_reader   folder:{path}    (super_readers)
- 폴더 parent:      folder:{parent}       parent         folder:{path}    (path 계층에서 자동 도출)
- permission 보유자: {holder}             holder         permission:{name} (holders)
- 폴더 게이트:      permission:{name}     gated_by       folder:{path}    (folders)
- 테이블 게이트:    permission:{name}     gated_by       table:{table}    (tables)
- SQL capability:   permission:{name}#holder {rel}       capability:sql   (sql)

시드는 추가식(멱등)이라 부서·사용자 개명 시 옛 튜플이 잔존한다. `--prune`를 주면
config(_build_tuples)에 없는 stale 튜플을 삭제해 라이브 store를 config와 정합화한다.
⚠️ 멤버십 source of truth는 OpenFGA이고 config는 부트스트랩 입력일 뿐이라(ADR-0044),
`--prune`는 개명·리셋 같은 의도적 재정합 전용이다 — 운영 중 manage_permission으로
부여된 튜플도 config에 없으면 삭제하므로 일상 운영에 쓰지 말 것.
사용법: `python -m scripts.seed_fga [--prune]`
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


def _build_tuples(users: list[dict], folders: dict, permissions: dict) -> list[dict]:
    tuples: list[dict] = []

    # 1) 멤버십(부서·역할·부서관리자) + admin JWT → capability:admin
    for user in users:
        uid = user["user_id"]
        for dept in user.get("departments", []):
            tuples.append({"user": f"user:{uid}", "relation": "member", "object": f"department:{dept}"})
        for role in user.get("fga_roles", []):
            tuples.append({"user": f"user:{uid}", "relation": "member", "object": f"role:{role}"})
        for dept in user.get("dept_admin_of", []):
            tuples.append({"user": f"user:{uid}", "relation": "admin", "object": f"department:{dept}"})
        if "admin" in user.get("roles", []):
            tuples.append({"user": f"user:{uid}", "relation": "justify_grant", "object": "capability:admin"})

    # 2) 폴더 구조(public/private/super_reader/parent) — 명시 권한은 permission이 담당(아래 3)
    for path, spec in folders.items():
        spec = spec or {}
        if spec.get("public"):
            tuples.append({"user": "user:*", "relation": "public_viewer", "object": f"folder:{path}"})
        if spec.get("private"):
            tuples.append({"user": "user:*", "relation": "private_flag", "object": f"folder:{path}"})
        for role in spec.get("super_readers", []):
            tuples.append({"user": f"role:{role}#member", "relation": "super_reader", "object": f"folder:{path}"})
        parent = _parent_of(path)
        if parent:
            tuples.append({"user": f"folder:{parent}", "relation": "parent", "object": f"folder:{path}"})

    # 3) permission 묶음(ADR-0051): holder 배정 + folder/table gated_by + capability#holder
    for name, pspec in permissions.items():
        pspec = pspec or {}
        perm = f"permission:{name}"
        for holder in pspec.get("holders", []):
            tuples.append({"user": holder, "relation": "holder", "object": perm})
        for path in pspec.get("folders", []):
            tuples.append({"user": perm, "relation": "gated_by", "object": f"folder:{path}"})
        for table in pspec.get("tables", []):
            tuples.append({"user": perm, "relation": "gated_by", "object": f"table:{table}"})
        for rel in pspec.get("sql", []):
            tuples.append({"user": f"{perm}#holder", "relation": rel, "object": "capability:sql"})

    return tuples


async def _prune(client: FGAClient, desired: list[dict]) -> list[tuple[str, str, str]]:
    """config(desired)에 없는 라이브 튜플(stale)을 삭제하고 삭제 목록을 반환한다.

    desired = _build_tuples(...) 결과. 라이브를 전수 읽어 차집합만 삭제(전체 wipe 아님 →
    런타임에 정당히 추가된 튜플은 desired에 포함되지 않으면 삭제되니 주의)."""
    desired_keys = {(t["user"], t["relation"], t["object"]) for t in desired}
    live = await client.list_all_tuples()
    stale = [k for k in live if k not in desired_keys]
    for user, relation, object_ in stale:
        await client.revoke_tuple(user, relation, object_)
    return stale


async def main(prune: bool = False) -> None:
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
    permissions = yaml.safe_load(Path("config/permissions.yaml").read_text())["permissions"]

    tuples = _build_tuples(users, folders, permissions)
    # 튜플마다 개별 write — 재실행 시 일부만 존재해도 멱등 처리되도록.
    for t in tuples:
        await client._write_fga_tuples([t])
        print(f"  {t['user']:32} {t['relation']:8} {t['object']}")

    pruned: list[tuple[str, str, str]] = []
    if prune:
        # write(추가) 이후에 prune(삭제) — 결과적으로 라이브 store == config.
        pruned = await _prune(client, tuples)
        for user, relation, object_ in pruned:
            print(f"  - prune {user:32} {relation:8} {object_}")

    await pool.close()
    print(f"FGA 시드 완료 ({len(tuples)} 튜플" + (f", prune {len(pruned)} 삭제)" if prune else ")"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FGA 시드 (config → 튜플)")
    parser.add_argument(
        "--prune", action="store_true",
        help="config(_build_tuples)에 없는 stale 튜플 삭제 — 개명 후 잔재 정리",
    )
    args = parser.parse_args()
    asyncio.run(main(prune=args.prune))
