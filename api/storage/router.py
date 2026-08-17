from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from telethon.tl.types import Channel

from core.telegram_client import telegram_manager
from core.palette import color_for, ext_for_name
from api.files.repo import File, Folder
from api.files.router import _get_shared_client
from config.auth import require_user
from config.database import get_session, close_session

router = APIRouter(prefix="/api/storage", tags=["Telegram Storage"])


def _get_visible_files(db, user_id: int, is_superuser: bool):
    """Get files visible to the user with access control."""
    from api.folders.catalog import list_user_files, list_user_folders
    folders = list_user_folders(db, user_id, is_superuser)
    folder_ids = [f.id for f in folders]
    if is_superuser:
        files = db.query(File).order_by(File.created_at.desc()).all()
    else:
        files = db.query(File).filter(
            (File.owner_user_id == user_id) |
            (File.uploaded_by_user_id == user_id) |
            (File.folder_id.in_(folder_ids))
        ).order_by(File.created_at.desc()).all()
    return files, folders


@router.get("/stats", summary="Thống kê lưu trữ từ DB", description="Tổng hợp dung lượng, số lượng file. Phân bố theo LOẠI FILE (mỗi loại 1 màu) có phần trăm.")
async def storage_stats(request: Request):
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        files, folders = _get_visible_files(db, user.id, is_superuser)

        total_storage = 0
        total_files = 0
        folder_stats = []
        ext_map: Dict[str, Dict] = {}

        for f in files:
            if f.size > 0:
                total_storage += f.size
                total_files += 1

                ext = ext_for_name(f.name)
                ext_from = ext_for_name(f.name)
                if ext not in ext_map:
                    ext_map[ext] = {
                        "ext": ext,
                        "mime_type": f.mime_type or "application/octet-stream",
                        "file_count": 0,
                        "size_bytes": 0,
                        "color": color_for(f.name, f.mime_type or ""),
                        "label": ext.upper(),
                    }
                ext_map[ext]["file_count"] += 1
                ext_map[ext]["size_bytes"] += f.size

        # Folder stats
        for folder in folders:
            folder_file_count = db.query(File).filter(File.folder_id == folder.id).count()
            folder_size = db.query(File).filter(File.folder_id == folder.id).with_entities(File.size).all()
            folder_size_bytes = sum(s[0] for s in folder_size)
            folder_stats.append({
                "id": folder.id,
                "name": folder.name,
                "file_count": folder_file_count,
                "size_bytes": folder_size_bytes,
            })

        ext_types = list(ext_map.values())
        for item in ext_types:
            item["percent"] = round((item["size_bytes"] / total_storage * 100), 1) if total_storage else 0
        ext_types.sort(key=lambda x: x["size_bytes"], reverse=True)

        return {
            "total_storage_used_bytes": total_storage,
            "total_file_count": total_files,
            "folders": folder_stats,
            "mime_types": ext_types,
        }
    finally:
        close_session(db)


@router.get("/duplicates", summary="Tìm file trùng lặp từ DB", description="Tìm các file có cùng tên và kích thước.")
async def storage_duplicates(request: Request):
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        files, folders = _get_visible_files(db, user.id, is_superuser)
        folder_map = {f.id: f.name for f in folders}

        file_map: Dict[tuple, list] = {}
        for f in files:
            key = (f.name, f.size)
            if key not in file_map:
                file_map[key] = []
            file_map[key].append({
                "id": f.message_id,
                "message_id": f.message_id,
                "folder_id": f.folder_id,
                "folder_name": folder_map.get(f.folder_id, "Saved Messages"),
                "name": f.name,
                "size": f.size,
                "mime_type": f.mime_type or "application/octet-stream",
                "created_at": f.created_at.isoformat() if f.created_at else "",
            })

        duplicates = [
            {"name": name, "size": size, "files": files}
            for (name, size), files in file_map.items()
            if len(files) > 1
        ]

        return duplicates
    finally:
        close_session(db)