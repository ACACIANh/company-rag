from openai import OpenAI

from core.config import Config
from core.reranker.base import Reranker
from core.reranker.llm_reranker import LLMReranker
from core.reranker.noop_reranker import NoOpReranker
from core.reranker.rrf_reranker import RRFReranker


def create_reranker(config: Config) -> Reranker:
    if config.reranker_type == "llm":
        client = OpenAI(
            api_key=config.reranker_api_key or config.openai_api_key,
            base_url=config.reranker_base_url or None,
        )
        return LLMReranker(client=client, model=config.reranker_model)
    if config.reranker_type == "rrf":
        return RRFReranker()
    return NoOpReranker()
