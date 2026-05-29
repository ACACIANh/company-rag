from app.graph.nodes.save_memory import save_memory_node


def test_save_memory_appends_qa_pair_to_empty_history():
    state = {"question": "연차 어떻게 써?", "answer": "15일입니다.", "chat_history": []}
    result = save_memory_node(state)

    assert result == {
        "chat_history": [
            {"role": "user", "content": "연차 어떻게 써?"},
            {"role": "assistant", "content": "15일입니다."},
        ]
    }


def test_save_memory_appends_to_existing_history():
    existing = [
        {"role": "user", "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    state = {"question": "새 질문", "answer": "새 답변", "chat_history": existing}
    result = save_memory_node(state)

    assert len(result["chat_history"]) == 4
    assert result["chat_history"][0]["content"] == "이전 질문"
    assert result["chat_history"][-1] == {"role": "assistant", "content": "새 답변"}


def test_save_memory_does_not_mutate_original_history():
    original = [{"role": "user", "content": "q"}]
    state = {"question": "new", "answer": "ans", "chat_history": original}
    save_memory_node(state)
    assert len(original) == 1


def test_save_memory_handles_missing_chat_history_key():
    state = {"question": "질문", "answer": "답변"}
    result = save_memory_node(state)
    assert len(result["chat_history"]) == 2
