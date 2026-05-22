def increment_retry_node(state: dict) -> dict:
    return {"retry_count": state["retry_count"] + 1}
