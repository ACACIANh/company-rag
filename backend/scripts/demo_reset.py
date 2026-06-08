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

# 데모 사이드바를 깨끗하게 — 시연/녹화로 쌓인 채팅 세션 정리.
# daesu/mido/joohwan은 전체, admin(이우진)은 오늘(KST) 것만(이전 기록 보존).
_SESSION_PURGE_ALL = ["user-daesu", "user-mido", "user-joohwan"]
_SESSION_PURGE_TODAY = ["user-admin"]


def session_cleanup_statements() -> list[tuple[str, str, list]]:
    """chat_sessions 정리용 (설명, SQL, params) 목록.

    chat_messages는 FK ON DELETE CASCADE로 함께 삭제된다.
    created_at은 UTC(TIMESTAMPTZ)이므로 "오늘"은 Asia/Seoul 기준으로 비교한다.
    """
    return [
        (
            "전체 삭제(daesu/mido/joohwan)",
            "DELETE FROM chat_sessions WHERE user_id = ANY($1::text[])",
            [_SESSION_PURGE_ALL],
        ),
        (
            "오늘(KST) 삭제(admin)",
            "DELETE FROM chat_sessions "
            "WHERE user_id = ANY($1::text[]) "
            "AND (created_at AT TIME ZONE 'Asia/Seoul')::date "
            "= (now() AT TIME ZONE 'Asia/Seoul')::date",
            [_SESSION_PURGE_TODAY],
        ),
    ]


async def main() -> None:
    config = load_config()

    print("[1/5] business 스키마 재시드…")
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

        print("[2/5] 데모 부여 권한 revoke…")
        for user, relation, obj in _DEMO_GRANTS:
            try:
                await fga.revoke_tuple(user, relation, obj)
                print(f"      revoked: {user} {relation} {obj}")
            except Exception as exc:
                print(f"      skip(이미 없음): {user} {relation} {obj} [{type(exc).__name__}]")

        print("[3/5] gate_audit_log 비우기…")
        await pool.execute("TRUNCATE gate_audit_log")

        print("[4/5] fga_permission_cache 비우기…")
        await pool.execute("TRUNCATE fga_permission_cache")

        print("[5/5] 데모 계정 채팅 세션 정리…")
        if await pool.fetchval("SELECT to_regclass('public.chat_sessions')") is None:
            print("      chat_sessions 없음 — 건너뜀")
        else:
            for desc, sql, params in session_cleanup_statements():
                status = await pool.execute(sql, *params)
                print(f"      {desc}: {status}")
    finally:
        if fga is not None:
            await fga.aclose()
        await pool.close()

    print("✅ 데모 초기화 완료 — 깨끗한 상태에서 시연 가능")


if __name__ == "__main__":
    asyncio.run(main())
