from unittest.mock import MagicMock
from shared.fga.models import UserPermission
from shared.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text="내용", source="doc.md") -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test-1"), score=0.9)


def _mock_fga(teams=None, personal_docs=None):
    client = MagicMock()
    teams = teams or []
    client.build_chroma_filter.return_value = {"sensitivity": "public"} if not teams else {
        "$or": [{"sensitivity": "public"}, {"$and": [{"team_id": {"$in": teams}}, {"sensitivity": "internal"}]}]
    }
    return client


def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result()]
    mock_fga = _mock_fga()

    state = {"question": "테스트 질문", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}
    result = retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert "documents" in result
    assert len(result["documents"]) == 1


def test_retrieve_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga()

    retrieve_node(
        {"question": "원본", "rewritten_question": "재작성", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    call_args = mock_retriever.retrieve.call_args
    assert call_args[0][0] == "재작성"


def test_retrieve_node_passes_where_filter():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga(teams=["team:dev"])
    mock_fga.build_chroma_filter.return_value = {"expected": "filter"}

    retrieve_node(
        {"question": "q", "user_id": "u1", "user_teams": ["team:dev"], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    _, kwargs = mock_retriever.retrieve.call_args
    assert kwargs["where_filter"] == {"expected": "filter"}


def test_retrieve_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []
    mock_fga = _mock_fga()

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": "", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    call_args = mock_retriever.retrieve.call_args
    assert call_args[0][0] == "원본 질문"
