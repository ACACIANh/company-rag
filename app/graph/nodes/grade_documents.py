import re

from shared.llm.base import LLMClient
from app.graph.prompts import GRADE_DOCUMENTS


def grade_documents_node(state: dict, *, llm: LLMClient) -> dict:
    if not state["documents"]:
        return {"relevance_score": 0.0}
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    prompt = GRADE_DOCUMENTS.format(question=state["rewritten_question"], context=context)
    response = llm.complete(prompt).strip()
    match = re.search(r"([01](?:\.\d+)?)", response)
    score = float(match.group(1)) if match else 0.0
    return {"relevance_score": min(max(score, 0.0), 1.0)}
