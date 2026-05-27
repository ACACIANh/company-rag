import asyncio
import logging
import uuid
from functools import partial
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.reranker.base import Reranker
from shared.retriever.base import Retriever
from shared.fga.client import FGAClient
from app.graph.edges import (
    route_after_confirm,
    route_after_grade,
    route_after_hallucination,
    route_after_router,
)
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.confirm import confirm_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.load_memory import load_memory_node
from app.graph.nodes.permission import permission_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node
from app.graph.nodes.save_memory import save_memory_node
from app.graph.nodes.multi_query import multi_query_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
from app.graph.state import AgentState


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
    reranker: Reranker | None = None,
    fga_client: FGAClient | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    if fga_client is None:
        raise ValueError("fga_client is required")
    g = StateGraph(AgentState)

    g.add_node("load_memory", load_memory_node)
    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("router", partial(router_node, llm=llm))
    g.add_node("permission", partial(permission_node, fga_client=fga_client))
    g.add_node("retrieve", partial(
        retrieve_node,
        retriever=retriever,
        fga_client=fga_client,
        reranker=reranker,
        retrieve_top_k=retrieve_top_k,
        top_k=top_k,
    ))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("multi_query", partial(multi_query_node, llm=llm))
    g.add_node("web_search", partial(web_search_node, retriever=web_search_retriever))
    g.add_node("confirm", confirm_node)
    g.add_node("tool_executor", tool_executor_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))
    g.add_node("save_memory", save_memory_node)

    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "rewrite_query")
    g.add_edge("rewrite_query", "router")

    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "doc_search": "permission",
            "multi_query": "multi_query",
            "web_search": "web_search",
            "tool_call": "confirm",
        },
    )
    g.add_edge("multi_query", "permission")

    g.add_edge("permission", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    g.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {"tool_executor": "tool_executor", "end": END},
    )
    g.add_edge("tool_executor", "generate")
    g.add_edge("web_search", "generate")

    g.add_edge("generate", "check_hallucination")
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"save_memory": "save_memory", "generate": "generate"},
    )
    g.add_edge("save_memory", END)

    if checkpointer is None:
        checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


def _ensure_thread_id(config: dict | None) -> dict:
    if config is None:
        return {"configurable": {"thread_id": str(uuid.uuid4())}}
    if "configurable" not in config:
        return {**config, "configurable": {"thread_id": str(uuid.uuid4())}}
    if "thread_id" not in config["configurable"]:
        return {**config, "configurable": {**config["configurable"], "thread_id": str(uuid.uuid4())}}
    return config


async def answer_question(
    graph: CompiledStateGraph,
    question: str,
    config: dict | None = None,
    user_id: str = "anonymous",
    allowed_doc_ids: list[str] | None = None,
    chat_history_fallback: list | None = None,
) -> Answer:
    config = _ensure_thread_id(config)
    existing = await graph.aget_state(config)
    chat_history = (existing.values or {}).get("chat_history", [])
    if not chat_history and chat_history_fallback:
        chat_history = chat_history_fallback

    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
        "rewrite_strategy": None,
        "multi_queries": [],
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": user_id,
        "allowed_doc_ids": allowed_doc_ids or [],
        "user_teams": [],
        "personal_doc_ids": [],
    }
    final = await graph.ainvoke(initial, config=config)
    return Answer(text=final["answer"], sources=final["citations"])


async def stream_answer(
    graph: CompiledStateGraph,
    question: str,
    config: dict,
    user_id: str,
    allowed_doc_ids: list[str],
    token_queue: asyncio.Queue,
    session_store: Any,
    session_id: str,
    is_new_session: bool,
) -> None:
    try:
        config = _ensure_thread_id(config)
        config = {**config, "configurable": {**config["configurable"], "token_queue": token_queue}}
        existing = await graph.aget_state(config)
        chat_history = (existing.values or {}).get("chat_history", [])
        if not chat_history and not is_new_session:
            stored = await session_store.get_messages(session_id)
            chat_history = [{"role": m.role, "content": m.content} for m in stored]

        initial: AgentState = {
            "question": question,
            "rewritten_question": "",
            "chat_history": chat_history,
            "route": "doc_search",
            "rewrite_strategy": None,
            "multi_queries": [],
            "documents": [],
            "relevance_score": 0.0,
            "retry_count": 0,
            "answer": "",
            "citations": [],
            "hallucination_passed": False,
            "confirmed": False,
            "tool_input": "",
            "user_id": user_id,
            "allowed_doc_ids": allowed_doc_ids or [],
            "user_teams": [],
            "personal_doc_ids": [],
        }

        final = await graph.ainvoke(initial, config=config)
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
        })
        try:
            if is_new_session:
                await session_store.create_session(session_id, user_id, question[:20])
            await session_store.add_message(session_id, "user", question, [])
            await session_store.add_message(session_id, "assistant", final["answer"], final["citations"])
        except Exception:
            logging.exception("session store write failed for session_id=%s", session_id)
        await token_queue.put({"type": "done", "session_id": session_id})
    except Exception as exc:
        await token_queue.put({"type": "error", "message": str(exc)})
        await token_queue.put({"type": "done", "session_id": session_id})
