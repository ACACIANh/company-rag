import asyncio
import logging
import uuid
from functools import partial
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from langchain_core.messages import RemoveMessage

from core.llm.base import LLMClient
from core.models import Answer
from core.reranker.base import Reranker
from core.retriever.base import Retriever
from core.fga.client import FGAClient
from core.config import load_config
from core.llm.factory import create_chat_llm
from app.graph.edges import (
    route_after_agent,
    route_after_tool_gate,
    route_after_grade,
    route_after_hallucination,
    route_after_router,
)
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.clarify import clarify_node
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
from app.graph.nodes.agent import agent_node
from app.graph.nodes.tool_gate import tool_gate_node
from app.graph.nodes.justify_execute import justify_execute_node
from app.graph.nodes.agent_answer import agent_answer_node
from app.graph.nodes.capability_node import capability_node
from app.graph.tools.registry import build_tool_registry
from app.graph.state import AgentState

_STREAM_CHUNK_SIZE = 3  # 의사 스트리밍 청크 크기(글자). 타이핑 효과용.


def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    reranker: Reranker | None = None,
    fga_client: FGAClient | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
    checkpointer: BaseCheckpointSaver | None = None,
    audit_sink: Any = None,
    sql_pool: Any = None,
    sql_rw_pool: Any = None,
    app_pool: Any = None,
    chat_model: Any = None,
) -> CompiledStateGraph:
    if fga_client is None:
        raise ValueError("fga_client is required")
    if chat_model is None:
        chat_model = create_chat_llm(load_config())
    registry = build_tool_registry(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool, fga_client=fga_client, app_pool=app_pool)
    bound = chat_model.bind_tools(registry.tool_defs)
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
    g.add_node("agent", partial(agent_node, chat_model=bound))
    g.add_node("tool_gate", partial(tool_gate_node, registry=registry, fga_client=fga_client, audit_sink=audit_sink))
    g.add_node("confirm", confirm_node)
    g.add_node("justify_execute", partial(justify_execute_node, registry=registry, audit_sink=audit_sink))
    g.add_node("agent_answer", agent_answer_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))
    g.add_node("capability", partial(capability_node, fga_client=fga_client))
    g.add_node("clarify", clarify_node)
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
            "agent": "agent",
            "capability": "capability",
            "clarify": "clarify",
        },
    )
    g.add_edge("multi_query", "permission")
    g.add_conditional_edges(
        "clarify",
        lambda state: state["route"],
        {
            "doc_search": "permission",
            "agent": "agent",
        },
    )

    g.add_edge("permission", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )

    # agent → 게이트된 에이전트 루프 (ADR-0023)
    g.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tool_gate": "tool_gate", "agent_answer": "agent_answer"},
    )
    g.add_conditional_edges(
        "tool_gate",
        route_after_tool_gate,
        {"confirm": "confirm", "agent": "agent"},
    )
    g.add_edge("confirm", "justify_execute")
    g.add_edge("justify_execute", "agent")
    g.add_edge("agent_answer", "save_memory")
    g.add_edge("capability", "save_memory")

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


def _interrupt_answer(final: dict) -> Answer:
    intr = final["__interrupt__"][0].value if isinstance(
        final["__interrupt__"][0].value, dict
    ) else {}
    if "options" in intr:
        return Answer(
            text=f"{intr.get('message', '방식을 선택해주세요.')} (스트리밍 모드에서 선택 가능합니다.)",
            sources=[],
        )
    actions = intr.get("actions", [])
    lines = "\n".join(f"- {a.get('tool')}: {a.get('planned_action')}" for a in actions)
    text = "이 작업은 사유 기재 후 실행됩니다. 실행하려면 사유를 회신하세요.\n" + lines
    return Answer(text=text, sources=[])


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
    chat_history_fallback: list | None = None,
) -> Answer:
    config = _ensure_thread_id(config)
    existing = await graph.aget_state(config)

    # 이전 호출이 interrupt로 멈춘 thread면, 이번 question을 사유로 보고 resume한다.
    if existing.next and existing.tasks and any(
        getattr(t, "interrupts", None) for t in existing.tasks
    ):
        final = await graph.ainvoke(
            Command(resume=question), config={**config, "recursion_limit": 25}
        )
        if "__interrupt__" in final:
            return _interrupt_answer(final)
        return Answer(text=final.get("answer", ""), sources=final.get("citations", []))

    chat_history = (existing.values or {}).get("chat_history", [])
    if not chat_history and chat_history_fallback:
        chat_history = chat_history_fallback

    # add_messages 리듀서는 [] 전달 시 삭제가 아닌 "추가 없음"으로 처리 →
    # 이전 체크포인트의 agent_messages가 그대로 유지돼 앵무새 반복 유발.
    # RemoveMessage로 이전 메시지를 명시적으로 삭제한다.
    prev_agent_msgs = (existing.values or {}).get("agent_messages", [])
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
        "allowed_folders": [],
        "justification": "",
        "agent_messages": [RemoveMessage(id=m.id) for m in prev_agent_msgs],
        "pending_tool_calls": [],
        "executed_sql": [],
        "route_confidence": 1.0,
    }
    final = await graph.ainvoke(initial, config={**config, "recursion_limit": 25})
    if "__interrupt__" in final:
        return _interrupt_answer(final)
    return Answer(text=final["answer"], sources=final["citations"])


async def stream_answer(
    graph: CompiledStateGraph,
    question: str,
    config: dict,
    user_id: str,
    token_queue: asyncio.Queue,
    session_store: Any,
    session_id: str,
    is_new_session: bool,
) -> None:
    try:
        config = _ensure_thread_id(config)
        existing = await graph.aget_state(config)

        # 이전 호출이 interrupt로 멈춘 thread면, 이번 question을 사유로 보고 resume한다.
        if existing.next and existing.tasks and any(
            getattr(t, "interrupts", None) for t in existing.tasks
        ):
            final = await graph.ainvoke(
                Command(resume=question), config={**config, "recursion_limit": 25}
            )
        else:
            chat_history = (existing.values or {}).get("chat_history", [])
            if not chat_history and not is_new_session:
                stored = await session_store.get_messages(session_id)
                chat_history = [{"role": m.role, "content": m.content} for m in stored]

            prev_agent_msgs = (existing.values or {}).get("agent_messages", [])
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
                "allowed_folders": [],
                "justification": "",
                "agent_messages": [RemoveMessage(id=m.id) for m in prev_agent_msgs],
                "pending_tool_calls": [],
                "executed_sql": [],
                "route_confidence": 1.0,
            }

            final = await graph.ainvoke(initial, config={**config, "recursion_limit": 25})

        if "__interrupt__" in final:
            intr_value = final["__interrupt__"][0].value if isinstance(
                final["__interrupt__"][0].value, dict
            ) else {}
            # 새 세션이 interrupt로 멈추면, 사유 제출(resume) 요청이 세션 소유권
            # 검사를 통과하도록 세션을 먼저 기록한다. 답변은 아직 없으므로 메시지는
            # 저장하지 않는다(완료 시 정상 경로에서 기록).
            if is_new_session:
                try:
                    await session_store.create_session(session_id, user_id, question[:20])
                except Exception:
                    logging.exception("session store create failed for session_id=%s", session_id)
            if "options" in intr_value:
                await token_queue.put({
                    "type": "clarify",
                    "message": intr_value.get("message", ""),
                    "options": intr_value.get("options", []),
                })
            else:
                await token_queue.put({"type": "interrupt", "actions": intr_value.get("actions", [])})
            await token_queue.put({"type": "done", "session_id": session_id})
            return
        answer = final["answer"]
        for i in range(0, len(answer), _STREAM_CHUNK_SIZE):
            await token_queue.put({"type": "token", "content": answer[i:i + _STREAM_CHUNK_SIZE]})
        await token_queue.put({
            "type": "sources",
            "sources": [s.source for s in final["citations"]],
            "route": final.get("route", "doc_search"),
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
