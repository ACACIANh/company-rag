from unittest.mock import MagicMock

from app.graph.nodes.sql_generate import sql_generate_node, _strip_code_fence


# ── _strip_code_fence ───────────────────────────────────────
def test_strip_plain_sql_unchanged():
    assert _strip_code_fence("SELECT 1") == "SELECT 1"


def test_strip_sql_code_fence():
    assert _strip_code_fence("```sql\nSELECT 1\n```") == "SELECT 1"


def test_strip_bare_code_fence():
    assert _strip_code_fence("```\nSELECT 1\n```") == "SELECT 1"


# ── sql_generate_node ───────────────────────────────────────
def test_generates_sql_into_state():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "SELECT * FROM business.employees"
    result = sql_generate_node({"question": "전직원 보여줘", "rewritten_question": ""}, llm=mock_llm)
    assert result["generated_sql"] == "SELECT * FROM business.employees"


def test_strips_code_fence_from_llm_output():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "```sql\nSELECT name FROM business.employees\n```"
    result = sql_generate_node({"question": "이름", "rewritten_question": ""}, llm=mock_llm)
    assert result["generated_sql"] == "SELECT name FROM business.employees"


def test_prompt_includes_question_and_schema():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "SELECT 1"
    sql_generate_node({"question": "매출 합계", "rewritten_question": "2025 매출 합계는?"}, llm=mock_llm)
    prompt = mock_llm.complete.call_args[0][0]
    assert "2025 매출 합계는?" in prompt       # rewritten_question 우선
    assert "business.employees" in prompt
    assert "business.sales" in prompt
