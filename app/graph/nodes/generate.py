from shared.llm.base import LLMClient
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
    citations = [d.chunk.source for d in state["documents"]]
    return {"answer": text, "citations": citations}
