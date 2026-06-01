"""FGA folder 권한별 검색 통합 테스트 (path 정확 매칭 pre-filter).

permission_node(get_readable_folders) → retrieve_node(build_pg_filter→path=ANY)를
mock retriever로 엮어 검증한다. ListObjects가 상속까지 푼 가시 폴더 목록을 정확 매칭하여,
private 하위 폴더가 상위(public) 권한으로 새지 않는지가 핵심 (ADR-0015).
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
    # ListObjects가 상속까지 푼 가시 폴더 목록을 주입 (prune 없이 그대로 사용)
    client.list_readable_folders = AsyncMock(return_value=folders)
    return client


def _mock_retriever(chunks: list[dict]):
    """build_pg_filter가 만든 ("path = ANY($1)", [allowed]) 의 정확 매칭을 시뮬레이션."""
    mock = AsyncMock()

    async def fake_retrieve(query, top_k=5, where_clause="", params=None):
        params = params or []
        allowed = params[0] if params else []  # build_pg_filter: ("path = ANY($1)", [allowed])
        results = [
            SearchResult(
                chunk=Chunk(text=c["text"], source=c["source"], chunk_id=c["source"]),
                score=0.9,
            )
            for c in chunks
            if c["path"] in allowed  # 정확 매칭 — prefix 확장 없음
        ]
        return results[:top_k]

    mock.retrieve = fake_retrieve
    return mock


async def _run(fga, retriever, question="질문"):
    state = {"user_id": "u1", "question": question}
    state.update(await permission_node(state, fga_client=fga))
    return await retrieve_node(state, retriever=retriever, fga_client=fga)


async def test_engineering_user_sees_ops_not_hr():
    # alice: ListObjects가 상속 풀어 반환한 가시 폴더 (hr private 제외)
    fga = _fga_with_folders(
        ["/company", "/company/common", "/company/engineering", "/company/engineering/ops"]
    )
    retriever = _mock_retriever([
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/company/engineering/ops"},
        {"text": "공개", "source": "common/benefits.md", "path": "/company/common"},
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever, "배포 절차"))["documents"]]
    assert "engineering/ops/deploy.md" in sources  # dept_viewer로 가시 → 정확 매칭 통과
    assert "common/benefits.md" in sources
    assert "hr/perf.md" not in sources  # hr 폴더는 가시 목록에 없음


async def test_hr_user_sees_hr_not_ops():
    fga = _fga_with_folders(["/company", "/company/common", "/company/engineering", "/company/hr"])
    retriever = _mock_retriever([
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/company/engineering/ops"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert "hr/perf.md" in sources
    assert "engineering/ops/deploy.md" not in sources


async def test_public_only_user_cannot_see_private():
    # carol(무소속): public 폴더만 가시. private(ops·hr)는 prefix로 새면 안 된다 — ADR-0015 결함 회귀.
    fga = _fga_with_folders(["/company", "/company/common", "/company/engineering"])
    retriever = _mock_retriever([
        {"text": "공개", "source": "common/benefits.md", "path": "/company/common"},
        {"text": "배포", "source": "engineering/ops/deploy.md", "path": "/company/engineering/ops"},
        {"text": "인사", "source": "hr/perf.md", "path": "/company/hr"},
    ])
    sources = [r.chunk.source for r in (await _run(fga, retriever))["documents"]]
    assert sources == ["common/benefits.md"]  # private 폴더 청크는 차단


async def test_no_folders_returns_nothing():
    fga = _fga_with_folders([])
    retriever = _mock_retriever([
        {"text": "공개", "source": "common/benefits.md", "path": "/company/common"},
    ])
    assert (await _run(fga, retriever))["documents"] == []
