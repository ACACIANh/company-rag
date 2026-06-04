from app.graph.prompts import (
    RAG_GENERATE,
    CHECK_HALLUCINATION,
    ROUTER_PROMPT,
    SQL_GENERATE_PROMPT,
    REWRITE_QUERY,
    _BUSINESS_SCHEMA,
)


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


# ── ROUTER_PROMPT: 데이터 원천 기준 + 경계 few-shot + 폴백 (ADR-0022) ──
def test_router_prompt_keeps_question_placeholder():
    """{question}, {chat_history}만 남고 {schema}는 정의 시점에 치환되어야 한다."""
    assert "{question}" in ROUTER_PROMPT
    assert "{chat_history}" in ROUTER_PROMPT
    assert "{schema}" not in ROUTER_PROMPT


def test_router_prompt_exposes_business_schema():
    """라우터가 SQL 생성과 같은 스키마 인식을 공유한다(데이터 원천 기준)."""
    assert _BUSINESS_SCHEMA in ROUTER_PROMPT
    assert "business.employees" in ROUTER_PROMPT
    assert "business.sales" in ROUTER_PROMPT


def test_router_prompt_criterion_covers_docs_vs_tools_not_verbs():
    """판정 축이 동작 동사가 아니라 '문서 서술 vs 도구 처리'여야 한다."""
    assert "문서 서술로 답되는가" in ROUTER_PROMPT
    # 옛 동사 나열("예약, 조회, 실행, 전송 등 동작")이 제거되어야 한다.
    assert "예약, 조회, 실행, 전송" not in ROUTER_PROMPT


def test_router_prompt_includes_permission_management():
    """agent 분기가 권한 관리도 포괄함이 명시되어야 한다 (ADR-0031)."""
    assert "권한 관리" in ROUTER_PROMPT
    assert "agent:none" in ROUTER_PROMPT


def test_router_prompt_has_boundary_fewshot_pairs():
    """'정책(문서) vs 내 수치(DB)' 대조쌍이 들어 있어야 한다."""
    assert "내 연차 며칠 남았어?" in ROUTER_PROMPT      # → agent
    assert "연차는 며칠까지 쌓을 수 있어?" in ROUTER_PROMPT  # → doc_search


def test_router_prompt_leans_doc_search_when_ambiguous():
    """불확실 구간은 doc_search로 기운다는 폴백 지침이 있어야 한다."""
    assert "모호하면 doc_search" in ROUTER_PROMPT


def test_router_prompt_has_rollback_fewshot():
    """이전 대화 맥락 기반 롤백/취소 패턴이 agent few-shot에 포함되어야 한다."""
    assert "롤백해줘" in ROUTER_PROMPT
    assert "취소해줘" in ROUTER_PROMPT


def test_sql_generate_shares_same_schema_constant():
    """스키마 drift 방지 — 라우터와 SQL 생성이 같은 단일 출처를 쓴다."""
    assert _BUSINESS_SCHEMA in SQL_GENERATE_PROMPT
    assert "{question}" in SQL_GENERATE_PROMPT
    assert "{schema}" not in SQL_GENERATE_PROMPT


# ── SQL 생성 프롬프트: 카테고리형 값 힌트 (ADR-0021) ──
def test_sql_generate_injects_value_hints():
    """카테고리형 컬럼의 실제 저장값(영문 코드)이 주입되고, format이 깨지지 않아야 한다."""
    assert "business.employees.department" in SQL_GENERATE_PROMPT
    assert "개발팀" in SQL_GENERATE_PROMPT      # value mismatch 처방
    assert "{value_hints}" not in SQL_GENERATE_PROMPT
    # format이 KeyError 없이 동작(값 힌트의 중괄호 오인 회귀 방지).
    rendered = SQL_GENERATE_PROMPT.format(question="엔지니어링 부서 평균 급여")
    assert "엔지니어링 부서 평균 급여" in rendered


def test_sql_generate_value_hints_exclude_pii():
    """PII 컬럼(salary·email)은 값 힌트로 노출되지 않는다."""
    hints_section = SQL_GENERATE_PROMPT.split("카테고리형 컬럼의 실제 저장값")[1]
    assert "salary" not in hints_section
    assert "email" not in hints_section


def test_rewrite_query_preserves_intent_not_doc_search_form():
    """요청·명령형 질문을 문서 조회형('절차/방법')으로 바꾸지 않도록 의도 보존 지침이 있어야 한다."""
    from app.graph.prompts import REWRITE_QUERY
    assert "의도와 행위 유형은 그대로 보존" in REWRITE_QUERY
    assert "{question}" in REWRITE_QUERY
    assert "{chat_history}" in REWRITE_QUERY
