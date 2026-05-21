# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# from langgraph.graph import END, StateGraph
# from nodes.router import GraphState, make_router_node
# from nodes.rag import make_rag_node
# from nodes.direct import make_direct_node


# def build_graph(llm, retriever):
#     graph = StateGraph(GraphState)

#     graph.add_node("router", make_router_node(llm))
#     graph.add_node("rag", make_rag_node(retriever, llm))
#     graph.add_node("direct", make_direct_node(llm))

#     graph.set_entry_point("router")
#     graph.add_conditional_edges(
#         "router",
#         lambda state: state["route"],
#         {"rag": "rag", "direct": "direct"},
#     )
#     graph.add_edge("rag", END)
#     graph.add_edge("direct", END)

#     return graph.compile()
