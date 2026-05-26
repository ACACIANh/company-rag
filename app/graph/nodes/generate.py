import asyncio

from langchain_core.runnables import RunnableConfig

from shared.llm.base import LLMClient
from shared.models import SourceRef
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE, RAG_GENERATE_NO_DOCS

_NO_DOC_NOTICE = (
    "⚠️ 관련 사내 문서를 찾지 못했습니다.\n"
    "일반 지식을 바탕으로 답변드립니다.\n\n---\n\n"
)
_RELEVANCE_THRESHOLD = 0.5


async def generate_node(state: dict, config: RunnableConfig | None = None, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"

    is_doc_search = state.get("route") == "doc_search"
    no_relevant_docs = (
        not state["documents"]
        or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD
    )

    queue: asyncio.Queue | None = (
        (config or {}).get("configurable", {}).get("token_queue")
    )

    if is_doc_search and no_relevant_docs:
        prompt = RAG_GENERATE_NO_DOCS.format(
            chat_history=history_text,
            question=question,
        )
        prefix = _NO_DOC_NOTICE
        citations = []
    else:
        context = "\n\n".join(d.chunk.text for d in state["documents"])
        prompt = RAG_GENERATE.format(
            context=context,
            question=question,
            chat_history=history_text,
        )
        prefix = ""
        citations = [
            SourceRef(
                source=d.chunk.source,
                document_id=d.chunk.metadata.get("document_id", ""),
                sensitivity=d.chunk.metadata.get("sensitivity", "public"),
                team_id=d.chunk.metadata.get("team_id", ""),
            )
            for d in state["documents"]
        ]

    if queue is not None:
        tokens = []
        if prefix:
            await queue.put({"type": "token", "content": prefix})
            tokens.append(prefix)
        async for token in llm.stream(prompt):
            await queue.put({"type": "token", "content": token})
            tokens.append(token)
        text = "".join(tokens)
    else:
        text = prefix + llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            model="unknown",
        )

    return {"answer": text, "citations": citations}
