from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from core.telegram_client import telegram_manager
from api.files.repo import Folder, File
from api.folders.catalog import list_user_folders, list_user_files
from config.database import get_session, close_session

router = APIRouter(prefix="/files", tags=["Web Files"])


@router.get("", response_class=_TemplateResponse)
async def index(request: Request, folder_id: Optional[int] = None, search: Optional[str] = None):
    current_user = request.state.current_user
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/auth/login")

    uid = current_user.id
    is_superuser = current_user.is_superuser

    await telegram_manager.ensure_connected(uid)
    if not telegram_manager.is_connected(uid):
        return RedirectResponse(url="/")

    db = get_session()
    try:
        folders_data = list_user_folders(db, uid, is_superuser)
        folders = []
        for f in folders_data:
            folders.append({
                "id": f.id,
                "name": f.name,
                "owner_user_id": f.owner_user_id,
                "is_public": f.is_public,
                "is_owner": f.owner_user_id == uid or is_superuser,
                "username": f.username,
            })
        folder_name_map = {f.id: f.name for f in folders_data}

        files_data = list_user_files(db, uid, is_superuser, folder_id, search)

        files = []
        for f in files_data[:1000]:
            can_manage = is_superuser or f.owner_user_id == uid or f.uploaded_by_user_id == uid
            files.append({
                "id": f.message_id,
                "message_id": f.message_id,
                "folder_id": f.folder_id,
                "name": f.name,
                "size": f.size,
                "mime_type": f.mime_type or "application/octet-stream",
                "created_at": f.created_at,
                "folder_name": folder_name_map.get(f.folder_id, "Saved Messages"),
                "can_manage": can_manage,
            })

        current_folder_name = "Saved Messages"
        if folder_id is not None:
            current_folder_name = folder_name_map.get(folder_id, "Saved Messages")
    finally:
        close_session(db)

    context = {
        "request": request,
        "title": "Quản lý File",
        "files": files,
        "folders": folders,
        "current_folder_id": folder_id,
        "search": search,
        "total": len(files),
        "page": 1,
        "total_pages": 1,
        "limit": 100,
    }
    return templates.TemplateResponse("files/index.html", context)
