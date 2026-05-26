"""
API 테스트용 공통 픽스처.
FGA 클라이언트를 passthrough mock으로 대체해 기존 테스트가
OpenFGA 서버 없이 동작하도록 한다.
"""
import pytest
from unittest.mock import MagicMock, patch

from shared.models import SourceRef


def _passthrough_filter(sources, uid):
    """sources를 그대로 통과시키되 SourceRef가 아닌 항목은 변환한다."""
    result = []
    for s in sources:
        if isinstance(s, SourceRef):
            result.append(s)
        else:
            result.append(SourceRef(source=str(s)))
    return result


@pytest.fixture(autouse=True)
def passthrough_fga():
    """_make_fga_client를 passthrough mock으로 교체.

    filter_sources는 입력 sources를 그대로 반환한다 (SourceRef 변환 포함).
    개별 테스트에서 patch("app.api.deps._make_fga_client")를 사용하면
    해당 with 블록이 우선 적용된다.
    """
    from app.api.deps import _make_fga_client as _orig
    _orig.cache_clear()

    mock_fga = MagicMock()
    mock_fga.filter_sources.side_effect = _passthrough_filter

    with patch("app.api.deps._make_fga_client", return_value=mock_fga):
        yield mock_fga
