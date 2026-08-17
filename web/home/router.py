import re
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from core.telegram_client import telegram_manager
from api.files.repo import Folder, File
from config.database import get_session, close_session

router = APIRouter(tags=["Home"])


@router.get("/", response_class=_TemplateResponse)
async def index(request: Request):
    current_user = request.state.current_user
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/auth/login")

    uid = current_user.id
    is_superuser = current_user.is_superuser

    await telegram_manager.ensure_connected(uid)
    # Chỉ admin mới cần kết nối Telegram; user thường vẫn vào dashboard được
    if not telegram_manager.is_connected(uid) and is_superuser:
        return RedirectResponse(url="/auth/tg-connect")

    db = get_session()
    try:
        me = await telegram_manager.get_me(uid)
        user = None
        recent_files = []
        folders = []
        stats = {"total_storage_used_bytes": 0, "total_file_count": 0}

        if me:
            user = {
                "first_name": getattr(me, "first_name", ""),
                "last_name": getattr(me, "last_name", ""),
                "username": getattr(me, "username", "") or "",
                "phone": getattr(me, "phone", "") or "",
            }
        if user and not (user.get("username") or user.get("phone")):
            user = None

        # Recent files from DB (last 5 uploaded by user)
        recent = db.query(File).filter(
            (File.owner_user_id == uid) | (is_superuser == True)
        ).order_by(File.created_at.desc()).limit(5).all()
        for f in recent:
            recent_files.append({
                "id": f.message_id,
                "message_id": f.message_id,
                "name": f.name,
                "size": f.size,
                "mime_type": f.mime_type or "application/octet-stream",
                "created_at": f.created_at,
            })

        # Folders from DB
        folders_data = db.query(Folder).filter(
            (Folder.owner_user_id == uid) | (Folder.is_public == 1) | (is_superuser == True)
        ).all()
        for f in folders_data:
            files_in_folder = db.query(File).filter(File.folder_id == f.id).count()
            folders.append({
                "id": f.id,
                "name": f.name,
                "file_size": files_in_folder,
            })

        # Stats from DB
        stats_files = db.query(File).filter(
            (File.owner_user_id == uid) | (is_superuser == True)
        )
        for f in stats_files.all():
            stats["total_storage_used_bytes"] += f.size
            stats["total_file_count"] += 1
    finally:
        close_session(db)

    context = {
        "request": request,
        "title": "Dashboard",
        "user": user,
        "stats": stats,
        "recent_files": recent_files,
        "folders": folders,
        "is_superuser": bool(is_superuser),
    }
    return templates.TemplateResponse("home/index.html", context)