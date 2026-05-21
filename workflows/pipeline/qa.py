from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.observability.cache import CachedEmbedder, CachedLLM, LRUCache
from shared.observability.tracer import Tracer
from shared.orchestrator import Context, Pipeline
from shared.reranker import NoOpReranker
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store

from workflows.pipeline.prompts import QA_PROMPT
from workflows.pipeline.steps import GenerateStep, RerankStep, RetrieveStep


_components = None


def _build_components():
    config = load_config()
    embedder = CachedEmbedder(
        SentenceTransformerEmbedder(config.embedding_model),
        LRUCache(max_size=4096),
    )
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    reranker = NoOpReranker()
    llm = CachedLLM(
        create_llm(config),
        LRUCache(max_size=512),
        model_name=config.llm_model,
    )
    return retriever, reranker, llm


def _get_components():
    global _components
    if _components is None:
        _components = _build_components()
    return _components


def run(question: str) -> Answer:
    retriever, reranker, llm = _get_components()
    tracer = Tracer()
    pipeline = Pipeline(
        steps=[
            RetrieveStep(retriever, top_k=10),
            RerankStep(reranker, top_k=5),
            GenerateStep(llm, QA_PROMPT),
        ],
        tracer=tracer,
    )
    ctx = pipeline.run(Context(query=question))
    sources = sorted({c.chunk.source for c in ctx.chunks})
    return Answer(
        text=ctx.answer_text or "",
        sources=sources,
        trace=tracer.dump(),
    )
