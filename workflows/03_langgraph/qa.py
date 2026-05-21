import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from graph.graph import build_graph
from shared.config import load_config
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    llm = create_llm(config)
    retriever = Retriever(store, embedder)

    graph = build_graph(llm, retriever)

    state = graph.invoke(
        {
            "question": question,
            "route": "",
            "context": [],
            "answer": "",
            "sources": [],
            "trace": [],
        }
    )

    return Answer(
        text=state["answer"],
        sources=state["sources"],
        trace=state["trace"],
    )
