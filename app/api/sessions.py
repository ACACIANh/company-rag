from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.fga.client import FGAClient
from shared.session.base import SessionStore
from app.api.deps import get_current_user, get_fga_client, get_session_store

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
def list_sessions(
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    return [
        SessionOut(thread_id=s.thread_id, title=s.title, created_at=s.created_at)
        for s in store.list_sessions(user["user_id"])
    ]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    fga_client: FGAClient = Depends(get_fga_client),
):
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    result = []
    for m in store.get_messages(session_id):
        if m.role == "assistant" and m.sources:
            visible = fga_client.filter_sources(m.sources, user["user_id"])
        else:
            visible = m.sources
        result.append(MessageOut(
            role=m.role,
            content=m.content,
            sources=[s.source for s in visible],
        ))
    return result


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(session_id, user["user_id"])
