# tests/shared/test_indexer.py
import os
import pytest
from unittest.mock import MagicMock
from shared.indexer.indexer import Indexer


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.add = MagicMock()
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]
    return embedder


@pytest.fixture
def docs_dir(tmp_path):
    (tmp_path / "policy.md").write_text("연차는 15일입니다. 모든 직원에게 적용됩니다.")
    return str(tmp_path)


def test_indexer_indexes_markdown_files(mock_store, mock_embedder, docs_dir):
    indexer = Indexer(
        vector_store=mock_store,
        embedding_service=mock_embedder,
        chunk_size=100,
        chunk_overlap=10,
    )

    count = indexer.index_directory(docs_dir)

    assert count > 0
    mock_store.add.assert_called_once()


def test_indexer_ignores_non_md_files(mock_store, mock_embedder, tmp_path):
    (tmp_path / "README.txt").write_text("이 파일은 무시됩니다.")
    mock_embedder.embed_batch.return_value = []
    indexer = Indexer(
        vector_store=mock_store, embedding_service=mock_embedder
    )

    count = indexer.index_directory(str(tmp_path))

    assert count == 0
    mock_store.add.assert_not_called()
