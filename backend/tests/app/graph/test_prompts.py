from app.graph.prompts import RAG_GENERATE, CHECK_HALLUCINATION


def test_rag_generate_keeps_format_fields():
    """format에 쓰이는 placeholder가 유지되어야 한다."""
    assert "{context}" in RAG_GENERATE
    assert "{question}" in RAG_GENERATE
    assert "{chat_history}" in RAG_GENERATE


def test_rag_generate_has_groundedness_constraint():
    """문서 근거 + 날조 금지 지침이 들어 있어야 한다."""
    assert "문서" in RAG_GENERATE
    assert "지어내" in RAG_GENERATE


def test_check_hallucination_keeps_format_fields():
    assert "{context}" in CHECK_HALLUCINATION
    assert "{answer}" in CHECK_HALLUCINATION


def test_check_hallucination_judges_factual_claims_not_style():
    """문체가 아니라 사실 주장 기준임이 명시되어야 한다."""
    assert "사실" in CHECK_HALLUCINATION
    assert "YES" in CHECK_HALLUCINATION and "NO" in CHECK_HALLUCINATION
