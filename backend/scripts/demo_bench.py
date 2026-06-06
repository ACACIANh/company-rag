"""데모 시나리오 반복 벤치마크 러너.

15장면(메모리 project-demo-scenario 기준)을 /chat API로 순차 전송하며
장면별 end-to-end 지연을 측정한다. HITL interrupt(④ clarify·⑥⑧⑨⑭ JUSTIFY)는
응답 텍스트에서 감지해 같은 session_id로 사유/선택을 회신(resume)한다.

회차마다 scripts.demo_reset로 상태를 깨끗이 되돌린다(business 재시드 + FGA revoke +
audit/cache truncate). 멱등.

각 장면 leg의 epoch 윈도우를 함께 기록하므로, 사후에 cost_*.jsonl과 교차해
장면별 LLM 호출 횟수를 셀 수 있다.

사용:
  cd backend && .venv/bin/python -m scripts.demo_bench --iterations 3 --label baseline
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

# (id, account, question, kind, resume_text|None)
# resume_text 는 interrupt 감지 시에만 같은 session_id로 회신.
SCENES = [
    ("01", "daesu", "Friday, 너는 무슨 일을 도와줄 수 있어?", "capability", None),
    ("02", "daesu", "내 현재 권한이 뭐야?", "permission", None),
    ("03", "daesu", "신입사원 온보딩 절차 알려줘", "rag", None),
    ("04", "daesu", "보안 관련해서 알려줘", "clarify", "사내 문서 검색 (RAG)"),
    ("05", "daesu", "표준 근로계약서 양식도 보여줘", "rag_block", None),
    ("06", "daesu", "인사팀 직원들 이름이랑 급여 보여줘", "sql_read", "감사 대비 인사 데이터 확인 목적입니다."),
    ("07", "daesu", "내 급여를 9천만원으로 올려줘", "sql_write_deny", None),
    ("08", "admin", "현재 미배정 노트북 목록 보여줘", "sql_read", "유휴 장비 재고 확인 목적입니다."),
    ("09", "admin", "오대수에게 NB-001 지급해줘", "sql_write", "신규 입사자 장비 지급 처리입니다."),
    ("10", "admin", "오대수에게 법무 문서 열람 권한 줘", "permission", "권한 부여를 승인합니다."),
    ("11", "admin", "오대수의 최근 활동 이력 보여줘", "audit", None),
    ("12", "daesu", "표준 근로계약서 양식 보여줘", "rag", None),
    ("13", "mido", "내 권한이 뭐야?", "permission", None),
    ("14", "joohwan", "미도를 개발팀에 추가해줘", "permission_delegate", "팀 재배치에 따른 개발팀 합류 처리입니다."),
    ("15", "mido", "내 권한이 뭐야?", "permission", None),
]

CREDENTIALS = {
    "daesu": "daesu123",
    "admin": "admin123",
    "mido": "mido123",
    "joohwan": "joohwan123",
}

# interrupt(사유/선택 필요) 감지 마커 — builder._interrupt_answer 기준
_INTERRUPT_MARKERS = ("사유를 회신", "스트리밍 모드에서 선택", "방식을 선택")


def _needs_resume(text: str) -> bool:
    return any(m in text for m in _INTERRUPT_MARKERS)


async def _login(client: httpx.AsyncClient, base_url: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for username, password in CREDENTIALS.items():
        r = await client.post(
            f"{base_url}/auth/token",
            json={"username": username, "password": password},
        )
        r.raise_for_status()
        tokens[username] = r.json()["access_token"]
    return tokens


async def _post_chat(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    question: str,
    session_id: str | None,
) -> tuple[dict, float, float, float]:
    """POST /chat. 반환: (응답json, 지연초, t_start_epoch, t_end_epoch)."""
    body: dict = {"question": question}
    if session_id is not None:
        body["session_id"] = session_id
    t_start = time.time()
    p0 = time.perf_counter()
    r = await client.post(
        f"{base_url}/chat",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    elapsed = time.perf_counter() - p0
    t_end = time.time()
    r.raise_for_status()
    return r.json(), elapsed, t_start, t_end


async def _run_demo_reset() -> float:
    """demo_reset를 서브프로세스로 실행. 반환: 소요초."""
    p0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "scripts.demo_reset",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        sys.stderr.write(out.decode(errors="replace"))
        raise RuntimeError(f"demo_reset 실패(rc={proc.returncode})")
    return time.perf_counter() - p0


async def _run_scene(
    client: httpx.AsyncClient, base_url: str, tokens: dict[str, str],
    scene: tuple, iteration: int,
) -> dict:
    sid_id, account, question, kind, resume_text = scene
    token = tokens[account]
    legs: list[dict] = []

    resp, elapsed, t0, t1 = await _post_chat(client, base_url, token, question, None)
    answer = resp.get("answer", "")
    session_id = resp.get("session_id")
    legs.append({
        "leg": "initial", "latency_s": round(elapsed, 3),
        "t_start": t0, "t_end": t1,
        "tools": resp.get("tools", []), "answer_len": len(answer),
        "interrupted": _needs_resume(answer),
    })

    if resume_text is not None and _needs_resume(answer):
        resp2, elapsed2, t0b, t1b = await _post_chat(
            client, base_url, token, resume_text, session_id
        )
        answer2 = resp2.get("answer", "")
        legs.append({
            "leg": "resume", "latency_s": round(elapsed2, 3),
            "t_start": t0b, "t_end": t1b,
            "tools": resp2.get("tools", []), "answer_len": len(answer2),
            "interrupted": _needs_resume(answer2),
        })

    total = round(sum(l["latency_s"] for l in legs), 3)
    return {
        "iteration": iteration, "scene": sid_id, "account": account,
        "kind": kind, "question": question,
        "scene_total_s": total, "legs": legs,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else Path(f"logs/bench_{args.label}.json")
    base_url = args.base_url.rstrip("/")

    records: list[dict] = []
    reset_times: list[float] = []
    run_start = time.time()

    async with httpx.AsyncClient(timeout=180.0) as client:
        tokens = await _login(client, base_url)
        print(f"[bench:{args.label}] 로그인 완료 ({len(tokens)}계정), {args.iterations}회 반복")

        for it in range(1, args.iterations + 1):
            if not args.no_reset:
                rt = await _run_demo_reset()
                reset_times.append(round(rt, 2))
                print(f"  [iter {it}] demo_reset {rt:.1f}s")
            for scene in SCENES:
                rec = await _run_scene(client, base_url, tokens, scene, it)
                records.append(rec)
                legs_desc = " + ".join(
                    f"{l['leg']}={l['latency_s']}s" for l in rec["legs"]
                )
                print(
                    f"  [iter {it}] {rec['scene']} {rec['account']:8} "
                    f"{rec['kind']:18} {rec['scene_total_s']:6.2f}s  ({legs_desc})"
                )

    run_end = time.time()

    # 장면별 집계 (회차 교차)
    by_scene: dict[str, list[float]] = {}
    for rec in records:
        by_scene.setdefault(rec["scene"], []).append(rec["scene_total_s"])
    scene_summary = {}
    for sid_id, vals in sorted(by_scene.items()):
        scene_summary[sid_id] = {
            "n": len(vals),
            "min": round(min(vals), 3),
            "median": round(statistics.median(vals), 3),
            "max": round(max(vals), 3),
        }

    # 회차별 총합
    iter_totals: dict[int, float] = {}
    for rec in records:
        iter_totals[rec["iteration"]] = iter_totals.get(rec["iteration"], 0.0) + rec["scene_total_s"]

    summary = {
        "label": args.label,
        "iterations": args.iterations,
        "run_window": {"start": run_start, "end": run_end},
        "reset_times_s": reset_times,
        "iter_totals_s": {k: round(v, 2) for k, v in iter_totals.items()},
        "median_iter_total_s": round(statistics.median(list(iter_totals.values())), 2),
        "scene_summary": scene_summary,
    }

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(
        {"summary": summary, "records": records}, ensure_ascii=False, indent=2
    ))

    print(f"\n[bench:{args.label}] 회차별 총합(초): {summary['iter_totals_s']}")
    print(f"[bench:{args.label}] 회차 총합 median: {summary['median_iter_total_s']}s")
    print(f"[bench:{args.label}] 결과 저장: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
