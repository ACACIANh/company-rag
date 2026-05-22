from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.edges import route_after_grade, route_after_hallucination
from app.graph.nodes.check_hallucination import check_hallucination_node
from app.graph.nodes.generate import generate_node
from app.graph.nodes.grade_documents import grade_documents_node
from app.graph.nodes.increment_retry import increment_retry_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.state import AgentState


def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("rewrite_query", partial(rewrite_query_node, llm=llm))
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("grade_documents", partial(grade_documents_node, llm=llm))
    g.add_node("increment_retry", increment_retry_node)
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_node("check_hallucination", partial(check_hallucination_node, llm=llm))

    g.add_edge(START, "rewrite_query")
    g.add_edge("rewrite_query", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_edge("increment_retry", "rewrite_query")
    g.add_edge("generate", "check_hallucination")

    g.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {"generate": "generate", "rewrite_retry": "increment_retry"},
    )
    g.add_conditional_edges(
        "check_hallucination",
        route_after_hallucination,
        {"end": END, "generate": "generate"},
    )

    return g.compile()


def answer_question(graph: CompiledStateGraph, question: str) -> Answer:
    initial: AgentState = {
        "question": question,
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
    }
    final = graph.invoke(initial)
    return Answer(text=final["answer"], sources=final["citations"])
