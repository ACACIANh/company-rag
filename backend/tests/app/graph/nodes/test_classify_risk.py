from unittest.mock import MagicMock

from app.graph.nodes.classify_risk import classify_risk_node
from core.sql.risk import (
    RISK_SELECT,
    RISK_BULK_SELECT,
    RISK_UPDATE_DELETE,
    RISK_DDL,
    RISK_DENY,
)


# ── AST 확정 등급은 LLM 보강 없이 그대로 (LLM 미호출) ────────
def test_update_delete_skips_llm():
    mock_llm = MagicMock()
    state = {"generated_sql": "UPDATE business.employees SET salary = 0"}
    result = classify_risk_node(state, llm=mock_llm)
    assert result["sql_risk"] == RISK_UPDATE_DELETE
    mock_llm.complete.assert_not_called()


def test_ddl_skips_llm():
    mock_llm = MagicMock()
    state = {"generated_sql": "DROP TABLE business.employees"}
    result = classify_risk_node(state, llm=mock_llm)
    assert result["sql_risk"] == RISK_DDL
    mock_llm.complete.assert_not_called()


def test_deny_skips_llm():
    mock_llm = MagicMock()
    state = {"generated_sql": "}{ invalid ]["}
    result = classify_risk_node(state, llm=mock_llm)
    assert result["sql_risk"] == RISK_DENY
    mock_llm.complete.assert_not_called()


# ── 순수 SELECT만 LLM이 대량/PII 보강 (상향만) ──────────────
def test_select_promoted_to_bulk_when_llm_yes():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "yes"
    state = {"generated_sql": "SELECT name, salary, email FROM business.employees"}
    result = classify_risk_node(state, llm=mock_llm)
    assert result["sql_risk"] == RISK_BULK_SELECT


def test_select_stays_select_when_llm_no():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "no"
    state = {"generated_sql": "SELECT name FROM business.employees WHERE emp_id = 'x'"}
    result = classify_risk_node(state, llm=mock_llm)
    assert result["sql_risk"] == RISK_SELECT


def test_select_prompt_includes_sql():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "no"
    sql = "SELECT salary FROM business.employees"
    classify_risk_node({"generated_sql": sql}, llm=mock_llm)
    prompt = mock_llm.complete.call_args[0][0]
    assert sql in prompt
