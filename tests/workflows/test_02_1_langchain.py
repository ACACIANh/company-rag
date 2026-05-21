import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from shared.models import Answer


def load_qa():
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../workflows/02_1_langchain_basic")
    )
    qa_path = os.path.join(base, "qa.py")
    sys.path.insert(0, base)
    spec = importlib.util.spec_from_file_location("qa_02_1", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer(mocker):
    qa = load_qa()

    mock_docs = [
        Document(page_content="연차는 15일", metadata={"source": "vacation.md", "score": 0.9})
    ]
    mock_retriever_adapter = MagicMock()
    mock_retriever_adapter.invoke.return_value = mock_docs
    mock_llm_adapter = MagicMock()
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "연차는 15일입니다."

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm")
    mocker.patch.object(qa, "LangChainRetrieverAdapter", return_value=mock_retriever_adapter)
    mocker.patch.object(qa, "LangChainLLMAdapter", return_value=mock_llm_adapter)
    mocker.patch.object(qa, "build_chain", return_value=mock_chain)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert answer.trace is not None
