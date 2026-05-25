from shared.fga.client import FGAClient
from shared.fga.models import UserPermission
from shared.models import SearchResult
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker
from shared.retriever.base import Retriever


def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    fga_client: FGAClient,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    query = state.get("rewritten_question") or state["question"]
    perm = UserPermission(
        user_id=state.get("user_id", "anonymous"),
        teams=state.get("user_teams", []),
        personal_docs=state.get("personal_doc_ids", []),
    )
    where_filter = fga_client.build_chroma_filter(perm)
    results: list[SearchResult] = retriever.retrieve(
        query, top_k=retrieve_top_k, where_filter=where_filter
    )
    _reranker = reranker or NoOpReranker()
    reranked = _reranker.rerank(query, results, top_k=top_k)
    return {"documents": reranked}
