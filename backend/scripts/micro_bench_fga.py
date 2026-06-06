"""권한 스냅샷 FGA 조회: 순차 vs 병렬 마이크로벤치.

OpenAI LLM 변동과 무관하게, 실 OpenFGA로 권한 스냅샷이 수행하는 ~15개 독립 FGA
round-trip을 (a) 순차(최적화 전 패턴) (b) 병렬(현재 코드) 두 방식으로 N회 측정해
중앙값을 비교한다. P1 최적화 효과의 노이즈 없는 증거.

사용: cd backend && .venv/bin/python -m scripts.micro_bench_fga --user user-admin -n 10
"""
import argparse
import asyncio
import statistics
import time

import asyncpg

from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.sql.gate import gate_decision
from app.graph.tools.permission_tool import _CAPABILITY_DISPLAY, _resolve_capabilities

_KNOWN_TABLES = ("employees", "equipment", "sales")


async def _seq_snapshot(fga: FGAClient, uid: str):
    """최적화 전 패턴: 5개 조회를 순차, capability·table도 순차 루프."""
    departments = await fga.user_departments(uid)
    roles = await fga.user_roles(uid)
    folders = await fga.get_readable_folders(uid)
    caps = []
    for _label, risk in _CAPABILITY_DISPLAY:
        decision, _ = await gate_decision(fga.check, uid, risk)
        caps.append(decision)
    tables = []
    for t in _KNOWN_TABLES:
        if await fga.check(f"user:{uid}", "viewer", f"table:{t}"):
            tables.append(t)
    return departments, roles, folders, caps, tables


async def _par_snapshot(fga: FGAClient, uid: str):
    """현재(최적화 후) 패턴: 5개 조회 gather + capability·table 내부도 병렬."""
    departments, roles, folders, caps, tables = await asyncio.gather(
        fga.user_departments(uid),
        fga.user_roles(uid),
        fga.get_readable_folders(uid),
        _resolve_capabilities(fga.check, uid),
        fga.user_accessible_tables(uid),
    )
    return departments, roles, folders, caps, tables


async def _time(coro_fn, fga, uid, n) -> list[float]:
    out = []
    for _ in range(n):
        await fga._cache.invalidate(uid)  # 폴더 캐시 콜드 통일(공정 비교)
        t0 = time.perf_counter()
        await coro_fn(fga, uid)
        out.append((time.perf_counter() - t0) * 1000)  # ms
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="user-admin")
    ap.add_argument("-n", type=int, default=10)
    args = ap.parse_args()

    config = load_config()
    pool = await asyncpg.create_pool(config.postgres_dsn, min_size=1, max_size=4)
    try:
        cache = make_cache_backend(config.fga_cache_backend, pool)
        if hasattr(cache, "ensure_table"):
            await cache.ensure_table()
        fga = FGAClient(
            config=FGAConfig(
                api_url=config.fga_api_url, store_id=config.fga_store_id,
                api_key=config.fga_api_key, cache_ttl_seconds=config.fga_cache_ttl_seconds,
            ),
            cache=cache, pg_pool=pool,
        )

        # 워밍업(커넥션·lazy import) — 측정에서 제외
        await _par_snapshot(fga, args.user)

        # 동작 동일성 확인
        seq_res = await _seq_snapshot(fga, args.user)
        par_res = await _par_snapshot(fga, args.user)
        same = (seq_res[0] == par_res[0] and seq_res[1] == par_res[1]
                and sorted(seq_res[4]) == sorted(par_res[4]))
        print(f"동작 동일성(부서·역할·테이블): {'OK' if same else 'MISMATCH!'}")

        seq = await _time(_seq_snapshot, fga, args.user, args.n)
        par = await _time(_par_snapshot, fga, args.user, args.n)

        sm, pm = statistics.median(seq), statistics.median(par)
        print(f"\n권한 스냅샷 FGA 조회 ({args.user}, n={args.n})")
        print(f"  순차(최적화 전): median {sm:7.1f} ms  (min {min(seq):.1f} / max {max(seq):.1f})")
        print(f"  병렬(최적화 후): median {pm:7.1f} ms  (min {min(par):.1f} / max {max(par):.1f})")
        if pm > 0:
            print(f"  → {sm/pm:.2f}× 빠름, {sm - pm:.0f} ms 단축 (장면당)")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
