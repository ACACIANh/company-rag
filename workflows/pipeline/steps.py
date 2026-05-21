from shared.llm.base import LLMClient
from shared.orchestrator import Context, Step
from shared.reranker.base import Reranker
from shared.retriever.base import Retriever


class RetrieveStep(Step):
    name = "retrieve"

    def __init__(self, retriever: Retriever, top_k: int = 10) -> None:
        self._retriever = retriever
        self._top_k = top_k

    def run(self, ctx: Context) -> Context:
        ctx.chunks = self._retriever.retrieve(ctx.query, top_k=self._top_k)
        return ctx


class RerankStep(Step):
    name = "rerank"

    def __init__(self, reranker: Reranker, top_k: int = 5) -> None:
        self._reranker = reranker
        self._top_k = top_k

    def run(self, ctx: Context) -> Context:
        ctx.chunks = self._reranker.rerank(ctx.query, ctx.chunks, top_k=self._top_k)
        return ctx


class GenerateStep(Step):
    name = "generate"

    def __init__(self, llm: LLMClient, prompt_template: str) -> None:
        self._llm = llm
        self._template = prompt_template

    def run(self, ctx: Context) -> Context:
        context_text = "\n\n".join(c.chunk.text for c in ctx.chunks)
        prompt = self._template.format(context=context_text, question=ctx.query)
        ctx.answer_text = self._llm.complete(prompt)
        return ctx
