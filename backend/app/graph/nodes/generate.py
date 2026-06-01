from langchain_core.runnables import RunnableConfig

from core.llm.base import LLMClient
from core.models import SourceRef
from core.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE

_NO_DOC_NOTICE = "⚠️ 관련 사내 문서를 찾지 못했습니다."
_RELEVANCE_THRESHOLD = 0.5


async def generate_node(state: dict, config: RunnableConfig | None = None, *, llm: LLMClient) -> dict:
    is_doc_search = state.get("route") == "doc_search"
    no_relevant_docs = (
        not state["documents"]
        or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD
    )

    # 내부 문서를 찾지 못하면 LLM 일반 지식 답변 대신 고지문만 반환
    if is_doc_search and no_relevant_docs:
        return {
            "answer": _NO_DOC_NOTICE,
            "citations": [],
            "hallucination_passed": True,
        }

    question = state.get("rewritten_question") or state["question"]
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"

    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = RAG_GENERATE.format(
        context=context,
        question=question,
        chat_history=history_text,
    )
    citations = [SourceRef(source=d.chunk.source) for d in state["documents"]]

    text = llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            model="unknown",
        )

    return {"answer": text, "citations": citations}
