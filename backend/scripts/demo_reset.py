"""데모 리허설 초기화 — 한 번 시연한 데모를 깨끗한 시작 상태로 되돌린다.

데모(15장면)가 바꾸는 상태를 모두 원복한다:
1. business 스키마 재시드 — ⑨ NB-001 지급 등 테이블 변경 원복(미배정 복구)
2. 데모가 grant한 FGA 튜플 revoke (시연 전 성립해야 할 전제 복구):
   - ⑩  user:user-daesu holder permission:법무  → ②/⑤ "법무 없음·차단"이 다시 성립
   - ⑭  user:user-mido  member department:개발   → ⑬ before(제품만)가 다시 성립
     (seed_fga는 일방향(추가만)이라 미도 개발 제거는 시드로 안 됨 — 여기서 직접 revoke)
3. gate_audit_log 비우기 — ⑪ 감사 화면을 깨끗하게
4. FGA 권한 캐시 비우기 — stale 권한 방지

사용: cd backend && .venv/bin/python -m scripts.demo_reset
"""
import asyncio

import asyncpg

from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from scripts.seed_business import main as seed_business_main

# 데모가 부여하는, 시연 전 원복해야 할 FGA 튜플 (멱등 — 없으면 무시)
_DEMO_GRANTS = [
    ("user:user-daesu", "holder", "permission:법무"),  # ⑩ 법무 문서 열람권
    ("user:user-mido", "member", "department:개발"),    # ⑭ 미도 개발팀 합류
]


async def main() -> None:
    config = load_config()

    print("[1/4] business 스키마 재시드…")
    await seed_business_main()

    pool = await asyncpg.create_pool(config.postgres_dsn, min_size=1, max_size=2)
    fga = None
    try:
        cache = make_cache_backend(config.fga_cache_backend, pool)
        fga = FGAClient(
            config=FGAConfig(
                api_url=config.fga_api_url,
                store_id=config.fga_store_id,
                api_key=config.fga_api_key,
                cache_ttl_seconds=config.fga_cache_ttl_seconds,
            ),
            cache=cache,
            pg_pool=pool,
        )

        print("[2/4] 데모 부여 권한 revoke…")
        for user, relation, obj in _DEMO_GRANTS:
            try:
                await fga.revoke_tuple(user, relation, obj)
                print(f"      revoked: {user} {relation} {obj}")
            except Exception as exc:
                print(f"      skip(이미 없음): {user} {relation} {obj} [{type(exc).__name__}]")

        print("[3/4] gate_audit_log 비우기…")
        await pool.execute("TRUNCATE gate_audit_log")

        print("[4/4] fga_permission_cache 비우기…")
        await pool.execute("TRUNCATE fga_permission_cache")
    finally:
        if fga is not None:
            await fga.aclose()
        await pool.close()

    print("✅ 데모 초기화 완료 — 깨끗한 상태에서 시연 가능")


if __name__ == "__main__":
    asyncio.run(main())
