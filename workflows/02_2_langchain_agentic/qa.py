import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agent.agent import build_agent_executor
from tools.rag_tool import make_rag_tool
from shared.config import load_config
from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    llm_client = create_llm(config)

    retriever = Retriever(store, embedder)
    rag_tool = make_rag_tool(retriever)
    llm_adapter = LangChainLLMAdapter(llm_client=llm_client)
    executor = build_agent_executor(llm_adapter, [rag_tool])

    result = executor.invoke({"input": question})

    trace = [
        {
            "thought": step[0].log.strip(),
            "action": step[0].tool,
            "observation": str(step[1]),
        }
        for step in result.get("intermediate_steps", [])
    ]

    sources = list(
        {
            part.split("]")[0][1:]
            for step in result.get("intermediate_steps", [])
            for obs in [str(step[1])]
            for part in obs.split("\n\n")
            if part.startswith("[")
        }
    )

    return Answer(text=result["output"], sources=sources, trace=trace)
