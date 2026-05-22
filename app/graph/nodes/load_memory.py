MAX_TURNS = 10


def load_memory_node(state: dict) -> dict:
    history = state.get("chat_history", [])
    return {"chat_history": history[-(MAX_TURNS * 2):]}
