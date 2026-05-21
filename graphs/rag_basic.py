"""기본 RAG 그래프: retrieve → generate 2노드 선형 그래프.

내부 섹션 구획 (추후 추출 친화):
  - State  → state/rag_state.py
  - Nodes  → nodes/retrieve.py, nodes/generate.py
  - Graph assembly
  - Eval adapter → graphs/adapters.py
"""

from langgraph.graph import MessagesState

from shared.models import SearchResult
from shared.retriever.base import Retriever


# ===== State =====


class RagState(MessagesState):
    retrieved_docs: list[SearchResult]


# ===== Nodes =====


def retrieve_node(state: RagState, *, retriever: Retriever) -> dict:
    query = state["messages"][-1].content
    results = retriever.retrieve(query, top_k=5)
    return {"retrieved_docs": results}
