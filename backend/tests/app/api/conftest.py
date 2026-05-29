"""
API 테스트용 공통 픽스처.
app.state를 mock으로 초기화해 lifespan/DB 없이 API 테스트가 동작하도록 한다.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.models import SourceRef


async def _passthrough_filter(sources, uid):
    return [s if isinstance(s, SourceRef) else SourceRef(source=str(s)) for s in sources]


@pytest.fixture(autouse=True)
def setup_app_state():
    """모든 API 테스트에서 app.state를 mock으로 초기화."""
    from app.api.chat import app

    mock_fga = MagicMock()
    mock_fga.filter_sources = AsyncMock(side_effect=_passthrough_filter)
    mock_fga.build_pg_filter = MagicMock(return_value=("sensitivity = 'public'", []))

    mock_session = AsyncMock()
    mock_session.list_sessions = AsyncMock(return_value=[])
    mock_session.create_session = AsyncMock()
    mock_session.add_message = AsyncMock()
    mock_session.get_messages = AsyncMock(return_value=[])
    mock_session.delete_session = AsyncMock()

    mock_store = AsyncMock()
    mock_store.count = AsyncMock(return_value=0)

    app.state.fga_client = mock_fga
    app.state.session_store = mock_session
    app.state.store = mock_store
    app.state.graph = MagicMock()
    app.state.pool = None

    yield mock_fga
