from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SessionMeta:
    thread_id: str
    title: str
    created_at: str  # ISO8601


@dataclass
class StoredMessage:
    role: str  # 'user' | 'assistant'
    content: str
    sources: list[str] = field(default_factory=list)


class SessionStore(ABC):
    @abstractmethod
    def create_session(self, thread_id: str, user_id: str, title: str) -> None: ...

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[SessionMeta]: ...

    @abstractmethod
    def get_messages(self, thread_id: str) -> list[StoredMessage]: ...

    @abstractmethod
    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[str]
    ) -> None: ...

    @abstractmethod
    def delete_session(self, thread_id: str, user_id: str) -> None: ...
