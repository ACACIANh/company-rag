from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.auth.base import AuthUser
from core.document_original.base import DocumentOriginalStore
from core.fga.client import FGAClient
from app.api.deps import get_current_user, get_fga_client, get_original_store

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/download")
async def download_document(
    document_id: str = Query(...),
    user: AuthUser = Depends(get_current_user),
    fga_client: FGAClient = Depends(get_fga_client),
    original_store: DocumentOriginalStore = Depends(get_original_store),
) -> StreamingResponse:
    rec = await original_store.get_latest(document_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Document not found")
    folders = await fga_client.get_readable_folders(user["user_id"])
    # 검색 pre-filter와 동일한 정확 매칭. 비가시 폴더는 존재를 숨겨 404.
    if rec.folder_path not in folders:
        raise HTTPException(status_code=404, detail="Document not found")
    return StreamingResponse(
        iter([rec.original_file]),
        media_type=rec.mime,
        headers={"Content-Disposition": f'attachment; filename="{rec.filename}"'},
    )
