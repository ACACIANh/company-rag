# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# import sys
# import os

# sys.path.insert(0, os.path.dirname(__file__))

# from agent.agent import build_agent_executor
# from tools.rag_tool import make_rag_tool
# from shared.config import load_config
# from shared.llm.factory import create_chat_llm
# from shared.models import Answer
# from shared.retriever.embedding import EmbeddingService
# from shared.retriever.retriever import Retriever
# from shared.vector_store.factory import create_vector_store


# def run(question: str) -> Answer:
#     config = load_config()
#     embedder = EmbeddingService(config.embedding_model)
#     store = create_vector_store(config)

#     retriever = Retriever(store, embedder)
#     rag_tool = make_rag_tool(retriever)
#     llm_adapter = create_chat_llm(config)
#     executor = build_agent_executor(llm_adapter, [rag_tool])

#     result = executor.invoke({"input": question})

#     trace = [
#         {
#             "thought": step[0].log.strip(),
#             "action": step[0].tool,
#             "observation": str(step[1]),
#         }
#         for step in result.get("intermediate_steps", [])
#     ]

#     sources = list(
#         {
#             part.split("]")[0][1:]
#             for step in result.get("intermediate_steps", [])
#             for obs in [str(step[1])]
#             for part in obs.split("\n\n")
#             if part.startswith("[")
#         }
#     )

#     return Answer(text=result["output"], sources=sources, trace=trace)
