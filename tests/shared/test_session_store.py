from shared.session.adapters.memory import InMemorySessionStore


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
