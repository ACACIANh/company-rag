from langgraph.types import interrupt


def confirm_node(state: dict) -> dict:
    action = state.get("tool_input") or state["rewritten_question"]
    user_response = interrupt({
        "message": f"다음 작업을 실행하시겠습니까?\n요청: {action}",
        "tool_input": action,
    })
    return {"confirmed": bool(user_response)}
