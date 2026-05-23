import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
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
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node
from app.graph.nodes.save_memory import save_memory_node
from app.graph.nodes.tool_executor import tool_executor_node
from app.graph.nodes.web_search import web_search_node
from app.graph.state import AgentState


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("load_memory", load_memory_node)
    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("router", partial(router_node, llm=llm))
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("web_search", partial(web_search_node, retriever=web_search_retriever))
    g.add_node("confirm", confirm_node)
    g.add_node("tool_executor", tool_executor_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))
    g.add_node("save_memory", save_memory_node)

    # 공통 진입: START → load_memory → rewrite_query → router
    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "rewrite_query")
    g.add_edge("rewrite_query", "router")

    # 라우터 → 세 경로 분기
    g.add_conditional_edges(
        "router",
        route_after_router,
        {"doc_search": "retrieve", "web_search": "web_search", "tool_call": "confirm"},
    )

    # doc_search 경로 (Self-RAG 루프)
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    # tool_call 경로
    g.add_conditional_edges(
        "confirm",
        route_after_confirm,
        {"tool_executor": "tool_executor", "end": END},
    )
    g.add_edge("tool_executor", "generate")

    # web_search 경로
    g.add_edge("web_search", "generate")

    # 공통 꼬리: generate → check_hallucination → save_memory → END
    g.add_edge("generate", "check_hallucination")
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"save_memory": "save_memory", "generate": "generate"},
    )
    g.add_edge("save_memory", END)

    return g.compile(checkpointer=MemorySaver())


def _ensure_thread_id(config: dict | None) -> dict:
    if config is None:
        return {"configurable": {"thread_id": str(uuid.uuid4())}}
    if "configurable" not in config:
        return {**config, "configurable": {"thread_id": str(uuid.uuid4())}}
    if "thread_id" not in config["configurable"]:
        return {**config, "configurable": {**config["configurable"], "thread_id": str(uuid.uuid4())}}
    return config


def answer_question(
    graph: CompiledStateGraph,
    question: str,
    config: dict | None = None,
    user_id: str = "anonymous",
    allowed_doc_ids: list[str] | None = None,
) -> Answer:
    config = _ensure_thread_id(config)
    existing = graph.get_state(config)
    chat_history = (existing.values or {}).get("chat_history", [])

    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": chat_history,
        "route": "doc_search",
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
    }
    final = graph.invoke(initial, config=config)
    return Answer(text=final["answer"], sources=final["citations"])
