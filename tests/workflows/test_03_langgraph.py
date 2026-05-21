# DEPRECATED: 대응 workflow가 주석 처리되어 비활성화됨.
# import importlib.util
# import os
# import sys
# import pytest
# from unittest.mock import MagicMock
# from shared.models import Answer


# def load_qa():
#     base = os.path.abspath(
#         os.path.join(os.path.dirname(__file__), "../../workflows/03_langgraph")
#     )
#     qa_path = os.path.join(base, "qa.py")
#     sys.path.insert(0, base)
#     spec = importlib.util.spec_from_file_location("qa_03", qa_path)
#     module = importlib.util.module_from_spec(spec)
#     spec.loader.exec_module(module)
#     sys.path.pop(0)
#     return module


# def test_run_rag_route(mocker):
#     qa = load_qa()

#     mock_graph = MagicMock()
#     mock_graph.invoke.return_value = {
#         "question": "연차 며칠이야?",
#         "route": "rag",
#         "answer": "연차는 15일입니다.",
#         "sources": ["vacation.md"],
#         "trace": [
#             {"node": "router", "route": "rag"},
#             {"node": "rag", "chunks_retrieved": 2},
#         ],
#     }
#     mocker.patch.object(qa, "load_config")
#     mocker.patch.object(qa, "EmbeddingService")
#     mocker.patch.object(qa, "create_vector_store")
#     mocker.patch.object(qa, "create_llm")
#     mocker.patch.object(qa, "Retriever")
#     mocker.patch.object(qa, "build_graph", return_value=mock_graph)

#     answer = qa.run("연차 며칠이야?")

#     assert isinstance(answer, Answer)
#     assert answer.text == "연차는 15일입니다."
#     assert "vacation.md" in answer.sources
#     assert answer.trace[0]["node"] == "router"


# def test_run_direct_route(mocker):
#     qa = load_qa()

#     mock_graph = MagicMock()
#     mock_graph.invoke.return_value = {
#         "question": "안녕하세요",
#         "route": "direct",
#         "answer": "안녕하세요! 무엇을 도와드릴까요?",
#         "sources": [],
#         "trace": [
#             {"node": "router", "route": "direct"},
#             {"node": "direct"},
#         ],
#     }
#     mocker.patch.object(qa, "load_config")
#     mocker.patch.object(qa, "EmbeddingService")
#     mocker.patch.object(qa, "create_vector_store")
#     mocker.patch.object(qa, "create_llm")
#     mocker.patch.object(qa, "Retriever")
#     mocker.patch.object(qa, "build_graph", return_value=mock_graph)

#     answer = qa.run("안녕하세요")

#     assert answer.trace[0]["route"] == "direct"
