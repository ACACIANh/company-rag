# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# import sys
# import os

# sys.path.insert(0, os.path.dirname(__file__))

# from chain.chain import build_chain
# from shared.config import load_config
# from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
# from shared.llm.factory import create_llm
# from shared.models import Answer
# from shared.retriever.embedding import EmbeddingService
# from shared.vector_store.adapters.langchain_retriever import LangChainRetrieverAdapter
# from shared.vector_store.factory import create_vector_store


# def run(question: str) -> Answer:
#     config = load_config()
#     embedder = EmbeddingService(config.embedding_model)
#     store = create_vector_store(config)
#     llm_client = create_llm(config)

#     retriever_adapter = LangChainRetrieverAdapter(
#         vector_store=store, embedding_service=embedder
#     )
#     llm_adapter = LangChainLLMAdapter(llm_client=llm_client)
#     chain = build_chain(retriever_adapter, llm_adapter)

#     result = chain.invoke(question)

#     text = result["text"]
#     docs = result["docs"]
#     sources = list({d.metadata["source"] for d in docs})
#     trace = [
#         {"step": "retriever", "docs_count": len(docs), "sources": sources},
#         {"step": "lcel_chain", "output": text},
#     ]

#     return Answer(text=text, sources=sources, trace=trace)
