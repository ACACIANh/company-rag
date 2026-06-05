import re

from langchain_core.runnables import RunnableConfig

from core.llm.base import LLMClient
from core.models import SourceRef
from core.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE, REGENERATE_GROUNDING_NOTICE

_NO_DOC_NOTICE = "⚠️ 관련 사내 문서를 찾지 못했습니다."
_RELEVANCE_THRESHOLD = 0.5
_CITATION_RE = re.compile(r'\[출처:\s*([\d,\s]+)\]')


def _parse_used_indices(text: str, total: int) -> list[int]:
    m = _CITATION_RE.search(text)
    if not m:
        return list(range(total))
    try:
        indices = [int(x.strip()) - 1 for x in m.group(1).split(",")]
        return [i for i in indices if 0 <= i < total]
    except ValueError:
        return list(range(total))


def _strip_citation_line(text: str) -> str:
    return _CITATION_RE.sub("", text).rstrip()


async def generate_node(state: dict, config: RunnableConfig | None = None, *, llm: LLMClient) -> dict:
    is_doc_search = state.get("route") == "doc_search"
    no_relevant_docs = (
        not state["documents"]
        or state.get("relevance_score", 1.0) < _RELEVANCE_THRESHOLD
    )

    if is_doc_search and no_relevant_docs:
        return {
            "answer": _NO_DOC_NOTICE,
            "citations": [],
            "hallucination_passed": True,
        }

    question = state.get("rewritten_question") or state["question"]
    history = state.get("chat_history", [])
    # ADR-0038: assistant 이전 답변 제거 — user 질문만 포함해 앵무새 반복 차단
    history_text = "\n".join(
        f"user: {m['content']}" for m in history if m["role"] == "user"
    ) if history else "없음"

    docs = state["documents"]
    context = "\n\n".join(f"[{i+1}] {d.chunk.text}" for i, d in enumerate(docs))
    prompt = RAG_GENERATE.format(
        context=context,
        question=question,
        chat_history=history_text,
    )
    # ADR-0053: 직전 답변이 있으면 hallucination 재시도(generate 재진입)다. 동일 입력 재호출을
    # 피하려 grounding 교정 지시를 덧붙여 입력을 바꾼다. (첫 생성에는 answer가 비어 미적용)
    if state.get("answer"):
        prompt += REGENERATE_GROUNDING_NOTICE

    text = llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            model="unknown",
        )

    # ADR-0037: LLM이 실제 사용한 문서만 citations로, 중복 source 제거
    used_indices = _parse_used_indices(text, len(docs))
    seen: set[str] = set()
    citations: list[SourceRef] = []
    for i in used_indices:
        src = docs[i].chunk.source
        if src not in seen:
            seen.add(src)
            citations.append(SourceRef(source=src))

    text = _strip_citation_line(text)

    return {"answer": text, "citations": citations}
