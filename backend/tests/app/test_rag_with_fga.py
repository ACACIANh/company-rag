"""FGA folder 권한별 검색 통합 테스트 (path prefix pre-filter).

permission_node(get_readable_folders→prune) → retrieve_node(build_pg_filter→path prefix)를
mock retriever로 엮어 검증한다. 상속 폴더(/engineering/ops)가 부모 권한으로 잡히는지가 핵심.
"""
from unittest.mock import AsyncMock

from core.fga.cache.memory import InMemoryCacheBackend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.models import Chunk, SearchResult
from app.graph.nodes.permission import permission_node
from app.graph.nodes.retrieve import retrieve_node


def _fga_with_folders(folders: list[str]) -> FGAClient:
    client = FGAClient(
        config=FGAConfig(api_url="http://localhost", store_id="test"),
        cache=InMemoryCacheBackend(),
    )
    # ListObjects 없이 동작하도록 raw 폴더 목록을 주입 (prune은 실제 로직 사용)
    client.list_readable_folders = AsyncMock(return_value=folders)
    return client


def _mock_retriever(chunks: list[dict]):
    """build_pg_filter가 만든 (where_clause, params)의 path prefix를 시뮬레이션."""
    mock = AsyncMock()

    async def fake_retrieve(query, top_k=5, where_clause="", params=None):
        params = params or []
        allowed = [params[i] for i in range(0, len(params), 2)]  # [folder, folder/%, ...]
        results = [
            SearchResult(
                chunk=Chunk(text=c["text"], source=c["source"], chunk_id=c["source"]),
                score=0.9,
            )
            for c in chunks
            if any(c["path"] == f or c["path"].startswith(f + "/") for f in allowed)
        ]
        return results[:top_k]

    mock.retrieve = fake_retrieve
    return mock


async def _run(fga, retriever, question="질문"):
    state = {"user_id": "u1", "question": question}
    state.update(await permission_node(state, fga_client=fga))
    return await retrieve_node(state, retriever=retriever, fga_client=fga)


async def test_engineering_user_sees_inherited_ops():
    fga = _fga_with_folders(["/company", "/engineering", "/engineering/ops"])
    retriever = _mock_retriever([
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/engineering/ops"},
        {"text": "공개", "source": "company/benefits.md", "path": "/company"},
        {"text": "인사", "source": "hr/perf.md", "path": "/hr"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever, "배포 절차"))["documents"]]
    assert "engineering/ops/deploy.md" in sources  # 상속 폴더가 /engineering prefix로 잡힘
    assert "company/benefits.md" in sources
    assert "hr/perf.md" not in sources


async def test_hr_user_sees_hr_not_engineering():
    fga = _fga_with_folders(["/company", "/hr"])
    retriever = _mock_retriever([
        {"text": "인사", "source": "hr/perf.md", "path": "/hr"},
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/engineering/ops"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert "hr/perf.md" in sources
    assert "engineering/ops/deploy.md" not in sources


async def test_company_only_user_no_engineering():
    fga = _fga_with_folders(["/company"])
    retriever = _mock_retriever([
        {"text": "공개", "source": "company/benefits.md", "path": "/company"},
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/engineering/ops"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert sources == ["company/benefits.md"]


async def test_no_folders_returns_nothing():
    fga = _fga_with_folders([])
    retriever = _mock_retriever([
        {"text": "공개", "source": "company/benefits.md", "path": "/company"},
    ])
    assert (await _run(fga, retriever))["documents"] == []
