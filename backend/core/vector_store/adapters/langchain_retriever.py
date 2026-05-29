from typing import Any
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field


class LangChainRetrieverAdapter(BaseRetriever):
    """core.VectorStore를 LangChain BaseRetriever(Runnable)로 래핑하는 어댑터."""

    vector_store: Any = Field(...)
    embedding_service: Any = Field(...)
    top_k: int = 5

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        embedding = self.embedding_service.embed(query)
        results = self.vector_store.search(embedding, top_k=self.top_k)
        return [
            Document(
                page_content=r.chunk.text,
                metadata={"source": r.chunk.source, "score": r.score},
            )
            for r in results
        ]
