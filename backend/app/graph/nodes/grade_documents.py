# 문서 관련성 게이트(Self-RAG). LLM 채점 대신 검색 top-cosine 임계로 판정해
# doc_search 경로의 LLM 왕복 1회를 제거한다. 임계는 scripts/calibrate_grade.py로 보정:
# off-topic(거부) 클러스터 max≈0.29 < eval(생성) 클러스터 min≈0.34, LLM-확정-관련 ≥0.385.
# 0.35는 두 클러스터 사이에 두어 off-topic을 거부하고 명백히 관련된 질문은 통과시킨다.
# 상세·롤백 절차: ADR-0056. (LLM 채점 프롬프트 GRADE_DOCUMENTS는 prompts.py에 보존)
_COSINE_RELEVANCE_THRESHOLD = 0.35


def grade_documents_node(state: dict) -> dict:
    documents = state["documents"]
    if not documents:
        return {"relevance_score": 0.0}
    # reranker가 순서를 바꿔도 견고하도록 최상위가 아닌 최대 cosine으로 판정.
    top_cosine = max(d.score for d in documents)
    relevant = top_cosine >= _COSINE_RELEVANCE_THRESHOLD
    return {"relevance_score": 1.0 if relevant else 0.0}
