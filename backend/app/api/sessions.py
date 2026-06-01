from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth.base import AuthUser
from core.session.base import SessionStore
from app.api.deps import get_current_user, get_session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    thread_id: str
    title: str
    created_at: str


class MessageOut(BaseModel):
    role: str
    content: str
    sources: list[str]


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    return [
        SessionOut(thread_id=s.thread_id, title=s.title, created_at=s.created_at)
        for s in await store.list_sessions(user["user_id"])
    ]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def get_session_messages(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    owned = {s.thread_id for s in await store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    # 권한 경계는 pre-filter(검색 시 allowed_folders)가 담당. 이력은 사용자 본인 것만
    # 보이며(세션 소유권 검사), 당시 정당하게 본 source만 담겨 있으므로 그대로 반환.
    return [
        MessageOut(role=m.role, content=m.content, sources=[s.source for s in m.sources])
        for m in await store.get_messages(session_id)
    ]


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    owned = {s.thread_id for s in await store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    await store.delete_session(session_id, user["user_id"])
