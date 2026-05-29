from app.graph.nodes.load_memory import load_memory_node, MAX_TURNS


def test_load_memory_returns_empty_when_no_history():
    result = load_memory_node({"chat_history": []})
    assert result == {"chat_history": []}


def test_load_memory_preserves_history_within_limit():
    history = [{"role": "user", "content": f"q{i}"} for i in range(5)]
    result = load_memory_node({"chat_history": history})
    assert result == {"chat_history": history}


def test_load_memory_trims_to_max_turns():
    # MAX_TURNS=10 → 20 메시지까지 허용
    history = [{"role": "user", "content": f"q{i}"} for i in range(25)]
    result = load_memory_node({"chat_history": history})
    assert len(result["chat_history"]) == MAX_TURNS * 2
    # 가장 오래된 메시지가 잘려야 함
    assert result["chat_history"][0]["content"] == "q5"
    assert result["chat_history"][-1]["content"] == "q24"


def test_load_memory_handles_missing_chat_history_key():
    result = load_memory_node({})
    assert result == {"chat_history": []}


def test_load_memory_trims_exactly_at_boundary():
    # 정확히 MAX_TURNS * 2 개 → 트리밍 없음
    history = [{"role": "user", "content": f"q{i}"} for i in range(MAX_TURNS * 2)]
    result = load_memory_node({"chat_history": history})
    assert len(result["chat_history"]) == MAX_TURNS * 2
