import json
from datetime import date
from pathlib import Path

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from core.auth.base import AuthUser
from app.api.deps import require_admin
from app.ingestion.indexer import build_index

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/index/status")
async def index_status(request: Request, _: AuthUser = Depends(require_admin)) -> dict:
    count = await request.app.state.store.count()
    return {"chunk_count": count}


@router.post("/index/rebuild", status_code=202)
def index_rebuild(
    background_tasks: BackgroundTasks,
    _: AuthUser = Depends(require_admin),
) -> dict:
    background_tasks.add_task(build_index, "docs/company")
    return {"status": "rebuilding"}


@router.post("/eval/run")
def eval_run(_: AuthUser = Depends(require_admin)) -> dict:
    import subprocess
    result = subprocess.run(
        ["python3", "tests/eval/runner.py"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {"stdout": result.stdout, "returncode": result.returncode}


@router.get("/eval/results")
def eval_results(_: AuthUser = Depends(require_admin)) -> list:
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    results = []
    for f in sorted(log_dir.glob("eval_*.jsonl"), reverse=True)[:10]:
        for line in f.read_text().splitlines():
            if line.strip():
                results.append(json.loads(line))
    return results


@router.get("/cost/report")
def cost_report(
    target_date: str = Query(default=None, description="YYYY-MM-DD, 기본값: 오늘"),
    _: AuthUser = Depends(require_admin),
) -> list:
    if target_date is None:
        target_date = date.today().isoformat()
    path = Path(f"logs/cost_{target_date}.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@router.get("/users")
def list_users(_: AuthUser = Depends(require_admin)) -> list:
    path = Path("config/users.yaml")
    users = yaml.safe_load(path.read_text())["users"]
    return [
        {
            "user_id": u["user_id"],
            "username": u["username"],
            "roles": u["roles"],
            "departments": u.get("departments", []),
        }
        for u in users
    ]


@router.post("/users/{user_id}/departments/{department_id}", status_code=204)
async def add_user_to_department(
    user_id: str,
    department_id: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> None:
    await request.app.state.fga_client.add_department_member(user_id, department_id)


@router.delete("/users/{user_id}/departments/{department_id}", status_code=204)
async def remove_user_from_department(
    user_id: str,
    department_id: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> None:
    await request.app.state.fga_client.remove_department_member(user_id, department_id)


@router.delete("/users/{user_id}", status_code=204)
async def offboard_user(
    user_id: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> None:
    await request.app.state.fga_client.delete_user_tuples(user_id)
