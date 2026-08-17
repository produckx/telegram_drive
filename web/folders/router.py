import re
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from core.telegram_client import telegram_manager
from api.files.repo import Folder, File
from config.database import get_session, close_session

router = APIRouter(prefix="/folders", tags=["Web Folders"])


@router.get("", response_class=_TemplateResponse)
async def index(request: Request):
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
        folders = db.query(Folder).filter(
            (Folder.owner_user_id == uid) | (Folder.is_public == 1) | (is_superuser == True)
        ).order_by(Folder.name.asc()).all()

        folders_list = []
        for f in folders:
            file_count = db.query(File).filter(File.folder_id == f.id).count() if f.id else 0
            folders_list.append({
                "id": f.id,
                "name": f.name,
                "username": f.username,
                "is_public": f.is_public,
                "owner_user_id": f.owner_user_id,
                "is_owner": f.owner_user_id == uid or is_superuser,
                "file_count": file_count,
            })
    finally:
        close_session(db)

    context = {
        "request": request,
        "title": "Quản lý Thư mục",
        "folders": folders_list,
    }
    return templates.TemplateResponse("folders/index.html", context)