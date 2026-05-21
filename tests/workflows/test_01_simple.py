import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock
from shared.models import Answer, Chunk, SearchResult


def load_qa():
    path = os.path.join(os.path.dirname(__file__), "../../workflows/01_simple/qa.py")
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("qa_01", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def test_run_returns_answer(mocker):
    # load_qa() 먼저 → 이후 patch.object로 해당 모듈의 이름공간을 직접 패치
    qa = load_qa()

    mock_results = [
        SearchResult(
            chunk=Chunk(text="연차는 15일입니다", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = mock_results
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "연차는 15일입니다."

    mocker.patch.object(qa, "load_config")
    mocker.patch.object(qa, "EmbeddingService")
    mocker.patch.object(qa, "create_vector_store")
    mocker.patch.object(qa, "create_llm", return_value=mock_llm)
    mocker.patch.object(qa, "Retriever", return_value=mock_retriever)

    answer = qa.run("연차 며칠이야?")

    assert isinstance(answer, Answer)
    assert answer.text == "연차는 15일입니다."
    assert "vacation.md" in answer.sources
    assert answer.trace is None
