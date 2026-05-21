import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from shared.models import Answer


def load_qa():
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../workflows/02_2_langchain_agentic")
    )
    qa_path = os.path.join(base, "qa.py")
    sys.path.insert(0, base)
    spec = importlib.util.spec_from_file_location("qa_02_2", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer_with_trace(mocker):
    qa = load_qa()

    mock_executor = MagicMock()
    mock_executor.invoke.return_value = {
        "output": "연차는 15일입니다.",
        "intermediate_steps": [
            (
                MagicMock(log="연차를 검색해야 한다", tool="search_company_docs"),
                "연차는 15일입니다.",
            )
        ],
    }

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "Retriever")
    mocker.patch.object(qa, "make_rag_tool")
    mocker.patch.object(qa, "LangChainLLMAdapter")
    mocker.patch.object(qa, "build_agent_executor", return_value=mock_executor)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert answer.trace is not None
    assert len(answer.trace) == 1
    assert answer.trace[0]["action"] == "search_company_docs"
