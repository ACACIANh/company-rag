# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# from shared.llm.base import LLMClient
# from nodes.router import GraphState

# _DIRECT_PROMPT = """\
# 다음 질문에 친절하게 한국어로 답하세요.

# 질문: {question}
# 답변:"""


# def make_direct_node(llm: LLMClient):
#     def direct_node(state: GraphState) -> GraphState:
#         answer = llm.complete(_DIRECT_PROMPT.format(question=state["question"]))
#         return {
#             **state,
#             "answer": answer,
#             "sources": [],
#             "trace": state.get("trace", []) + [{"node": "direct"}],
#         }
#     return direct_node
