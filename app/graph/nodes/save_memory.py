def save_memory_node(state: dict) -> dict:
    updated = list(state.get("chat_history", [])) + [
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": state["answer"]},
    ]
    return {"chat_history": updated}
