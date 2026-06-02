import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException


def _user(uid="u1"):
    return {"user_id": uid, "roles": ["employee"], "departments": []}


def _rec(folder="/c/eng"):
    from core.document_original.base import OriginalRecord

    return OriginalRecord(
        document_id="/c/eng/a.pdf", version=1, folder_path=folder,
        filename="a.pdf", mime="application/pdf",
        original_file=b"PDFDATA", content_hash="h",
    )


@pytest.mark.asyncio
async def test_download_allowed_folder_returns_stream():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/eng", "/c/hr"])
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=_rec("/c/eng"))

    resp = await download_document(
        document_id="/c/eng/a.pdf", user=_user(), fga_client=fga, original_store=store
    )
    assert resp.media_type == "application/pdf"
    assert 'filename="a.pdf"' in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_forbidden_folder_404():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/hr"])  # eng 비가시
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=_rec("/c/eng"))

    with pytest.raises(HTTPException) as exc:
        await download_document(
            document_id="/c/eng/a.pdf", user=_user(), fga_client=fga, original_store=store
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_document_404():
    from app.api.documents import download_document

    fga = AsyncMock()
    fga.get_readable_folders = AsyncMock(return_value=["/c/eng"])
    store = AsyncMock()
    store.get_latest = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await download_document(
            document_id="/c/eng/missing.pdf", user=_user(), fga_client=fga, original_store=store
        )
    assert exc.value.status_code == 404
