import os

import pytest

from shared.session.adapters.memory import InMemorySessionStore
from shared.session.adapters.postgres import PostgresSessionStore


def _store() -> InMemorySessionStore:
    return InMemorySessionStore()


def test_create_and_list():
    store = _store()
    store.create_session("t1", "alice", "첫 번째 질문")
    sessions = store.list_sessions("alice")
    assert len(sessions) == 1
    assert sessions[0].thread_id == "t1"
    assert sessions[0].title == "첫 번째 질문"


def test_list_only_own_sessions():
    store = _store()
    store.create_session("t1", "alice", "앨리스 질문")
    store.create_session("t2", "bob", "밥 질문")
    assert len(store.list_sessions("alice")) == 1
    assert len(store.list_sessions("bob")) == 1


def test_add_and_get_messages():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.add_message("t1", "user", "안녕?", [])
    store.add_message("t1", "assistant", "안녕하세요!", ["doc.md"])
    msgs = store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources == ["doc.md"]


def test_delete_session():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.delete_session("t1", "alice")
    assert store.list_sessions("alice") == []
    assert store.get_messages("t1") == []


def test_delete_does_not_affect_other_user():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.delete_session("t1", "bob")  # 다른 유저 — 무시해야 함
    assert len(store.list_sessions("alice")) == 1


def test_create_session_idempotent():
    store = _store()
    store.create_session("t1", "alice", "첫 질문")
    store.create_session("t1", "alice", "다른 제목")  # 두 번째 호출은 무시
    assert len(store.list_sessions("alice")) == 1
    assert store.list_sessions("alice")[0].title == "첫 질문"


def test_add_message_to_nonexistent_session_is_noop():
    store = _store()
    store.add_message("ghost", "user", "내용", [])  # 오류 없이 무시
    assert store.get_messages("ghost") == []



@pytest.fixture
def pg_store():
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set")
    store = PostgresSessionStore(dsn=dsn)
    with store._conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chat_sessions WHERE user_id IN ('alice', 'bob')")
    yield store
    with store._conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chat_sessions WHERE user_id IN ('alice', 'bob')")


def test_pg_create_and_list(pg_store):
    pg_store.create_session("t1", "alice", "첫 번째 질문")
    sessions = pg_store.list_sessions("alice")
    assert len(sessions) == 1
    assert sessions[0].thread_id == "t1"
    assert sessions[0].title == "첫 번째 질문"


def test_pg_list_only_own_sessions(pg_store):
    pg_store.create_session("t1", "alice", "앨리스 질문")
    pg_store.create_session("t2", "bob", "밥 질문")
    assert len(pg_store.list_sessions("alice")) == 1
    assert len(pg_store.list_sessions("bob")) == 1


def test_pg_add_and_get_messages(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.add_message("t1", "user", "안녕?", [])
    pg_store.add_message("t1", "assistant", "안녕하세요!", ["doc.md"])
    msgs = pg_store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources == ["doc.md"]


def test_pg_delete_session(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.delete_session("t1", "alice")
    assert pg_store.list_sessions("alice") == []
    assert pg_store.get_messages("t1") == []


def test_pg_delete_does_not_affect_other_user(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.delete_session("t1", "bob")
    assert len(pg_store.list_sessions("alice")) == 1


def test_pg_create_session_idempotent(pg_store):
    pg_store.create_session("t1", "alice", "첫 질문")
    pg_store.create_session("t1", "alice", "다른 제목")
    assert len(pg_store.list_sessions("alice")) == 1
    assert pg_store.list_sessions("alice")[0].title == "첫 질문"


def test_pg_add_message_to_nonexistent_session_is_noop(pg_store):
    pg_store.add_message("ghost", "user", "내용", [])
    assert pg_store.get_messages("ghost") == []
