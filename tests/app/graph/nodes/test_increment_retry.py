from app.graph.nodes.increment_retry import increment_retry_node


def test_increment_retry_increments_count():
    result = increment_retry_node({"retry_count": 0})
    assert result == {"retry_count": 1}


def test_increment_retry_increments_from_nonzero():
    result = increment_retry_node({"retry_count": 1})
    assert result == {"retry_count": 2}
