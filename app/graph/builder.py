from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer
from shared.retriever.base import Retriever
from app.graph.nodes.generate import generate_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.state import AgentState


def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(AgentState)
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
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
