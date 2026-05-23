import json
import logging

from openai import OpenAI

from shared.models import SearchResult
from shared.reranker.base import Reranker

logger = logging.getLogger(__name__)

_PROMPT = """\
질문과 문서 목록이 주어집니다. 각 문서를 질문과의 관련성 기준으로 재정렬하세요.

질문: {query}

문서 목록:
{docs}

관련성이 높은 순서대로 문서 번호만 JSON 배열로 반환하세요. 예: [2, 0, 1]
번호 외 다른 텍스트는 출력하지 마세요."""


class LLMReranker(Reranker):
    """OpenAI 호환 API로 listwise 재정렬.

    base_url을 사내 LLM 엔드포인트로 변경하면 그대로 전환됩니다.
    """

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        if not results:
            return []

        docs_text = "\n".join(
            f"[{i}] {r.chunk.text[:300]}" for i, r in enumerate(results)
        )
        prompt = _PROMPT.format(query=query, docs=docs_text)

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=128,
            )
            raw = resp.choices[0].message.content or ""
            ranked_indices = self._parse_indices(raw, len(results))
        except Exception as e:
            logger.warning("LLMReranker 실패, 원래 순서 유지: %s", e)
            ranked_indices = list(range(len(results)))

        reranked = [results[i] for i in ranked_indices]
        return reranked[:top_k] if top_k is not None else reranked

    def _parse_indices(self, raw: str, n: int) -> list[int]:
        try:
            indices = json.loads(raw.strip())
            if isinstance(indices, list) and all(isinstance(i, int) for i in indices):
                valid = [i for i in indices if 0 <= i < n]
                missing = [i for i in range(n) if i not in valid]
                return valid + missing
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning("LLMReranker 응답 파싱 실패, 원래 순서 유지: %r", raw)
        return list(range(n))
