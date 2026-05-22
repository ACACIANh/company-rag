from shared.llm.base import LLMClient
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = RAG_GENERATE.format(context=context, question=question, chat_history=history_text)
    text = llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        input_tokens = len(prompt) // 4
        output_tokens = len(text) // 4
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="unknown",
        )

    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
