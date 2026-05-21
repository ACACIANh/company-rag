"""기본 RAG 그래프: retrieve → generate 2노드 선형 그래프.

내부 섹션 구획 (추후 추출 친화):
  - State  → state/rag_state.py
  - Nodes  → nodes/retrieve.py, nodes/generate.py
  - Graph assembly
  - Eval adapter → graphs/adapters.py
"""

from functools import partial

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shared.llm.base import LLMClient
from shared.models import Answer, SearchResult
from shared.retriever.base import Retriever


# ===== State =====


class RagState(MessagesState):
    retrieved_docs: list[SearchResult]


# ===== Nodes =====


def retrieve_node(state: RagState, *, retriever: Retriever) -> dict:
    query = state["messages"][-1].content
    results = retriever.retrieve(query, top_k=5)
    return {"retrieved_docs": results}


def generate_node(state: RagState, *, llm: LLMClient) -> dict:
    question = state["messages"][-1].content
    context = "\n\n".join(d.chunk.text for d in state["retrieved_docs"])
    prompt = f"context:\n{context}\n\nquestion: {question}\nanswer in Korean."
    text = llm.complete(prompt)
    return {"messages": [AIMessage(content=text)]}


# ===== Graph assembly =====


def build_graph(retriever: Retriever, llm: LLMClient) -> CompiledStateGraph:
    g = StateGraph(RagState)
    g.add_node("retrieve", partial(retrieve_node, retriever=retriever))
    g.add_node("generate", partial(generate_node, llm=llm))
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


# ===== Eval adapter =====


def answer_question(graph: CompiledStateGraph, question: str) -> Answer:
    final = graph.invoke({"messages": [HumanMessage(content=question)]})
    sources = [d.chunk.source for d in final["retrieved_docs"]]
    return Answer(text=final["messages"][-1].content, sources=sources)
