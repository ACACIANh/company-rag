from datetime import datetime, timezone

from shared.models import SourceRef
from shared.session.base import SessionMeta, SessionStore, StoredMessage


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, SessionMeta]] = {}
        self._messages: dict[str, list[StoredMessage]] = {}

    async def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        if thread_id in self._sessions:
            return
        meta = SessionMeta(
            thread_id=thread_id,
            title=title,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sessions[thread_id] = (user_id, meta)
        self._messages[thread_id] = []

    async def list_sessions(self, user_id: str) -> list[SessionMeta]:
        result = [
            meta
            for uid, meta in self._sessions.values()
            if uid == user_id
        ]
        return sorted(result, key=lambda m: m.created_at, reverse=True)

    async def get_messages(self, thread_id: str) -> list[StoredMessage]:
        return list(self._messages.get(thread_id, []))

    async def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        if thread_id not in self._messages:
            return
        self._messages[thread_id].append(
            StoredMessage(role=role, content=content, sources=sources)
        )

    async def delete_session(self, thread_id: str, user_id: str) -> None:
        entry = self._sessions.get(thread_id)
        if entry is None or entry[0] != user_id:
            return
        del self._sessions[thread_id]
        del self._messages[thread_id]
