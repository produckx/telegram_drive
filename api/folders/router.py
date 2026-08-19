from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.auth import require_user, require_auth
from api.folders.catalog import (
    create_folder,
    update_folder,
    delete_folder,
    get_folder,
    can_access_folder,
    can_manage_folder,
    list_user_folders,
    count_folder_files,
)
from config.database import get_session, close_session

router = APIRouter(prefix="/api/folders", tags=["Telegram Folders"])


class CreateFolderRequest(BaseModel):
    name: str
    is_public: bool = False
    username: Optional[str] = None


class RenameFolderRequest(BaseModel):
    name: str


class VisibilityRequest(BaseModel):
    is_public: bool = False
    username: Optional[str] = None


@router.get("", summary="Danh sách thư mục", description="User thấy folders của mình + folders công khai. Admin thấy tất cả.")
@require_auth
async def list_folders(request: Request):
    user = require_user(request)
    db = get_session()
    try:
        folders = list_user_folders(db, user.id, user.is_superuser)
        result = []
        for f in folders:
            result.append({
                "id": f.id,
                "owner_user_id": f.owner_user_id,
                "name": f.name,
                "username": f.username,
                "is_public": bool(f.is_public),
                "is_owner": f.owner_user_id == user.id or user.is_superuser,
                "file_count": count_folder_files(db, f.id),
            })
        return {"success": True, "data": result}
    finally:
        close_session(db)


@router.post("", summary="Tạo thư mục mới", description="Tạo thư mục trong database (không tạo kênh Telegram).")
@require_auth
async def create_folder_endpoint(data: CreateFolderRequest, request: Request):
    user = require_user(request)
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="Tên thư mục không được để trống")

    db = get_session()
    try:
        folder = create_folder(
            db,
            owner_user_id=user.id,
            name=data.name.strip(),
            is_public=data.is_public,
            username=data.username,
        )
        return {
            "success": True,
            "data": {
                "id": folder.id,
                "name": folder.name,
                "username": folder.username,
                "is_public": bool(folder.is_public),
                "is_owner": True,
            },
        }
    finally:
        close_session(db)


@router.patch("/{folder_id}", summary="Đổi tên thư mục", description="Chỉ chủ sở hữu hoặc admin mới đổi tên được.")
@require_auth
async def rename_folder(folder_id: int, data: RenameFolderRequest, request: Request):
    user = require_user(request)
    db = get_session()
    try:
        folder = get_folder(db, folder_id)
        if not can_manage_folder(folder, user.id, user.is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền đổi tên thư mục này")
        if not data.name or not data.name.strip():
            raise HTTPException(status_code=400, detail="Tên thư mục không được để trống")
        updated = update_folder(db, folder_id, name=data.name.strip())
        return {"success": True, "message": f"Đã đổi tên thành {updated.name}"}
    finally:
        close_session(db)


@router.post("/{folder_id}/visibility", summary="Công khai / riêng tư thư mục", description="Chỉ chủ sở hữu hoặc admin đổi được.")
@require_auth
async def toggle_visibility(folder_id: int, data: VisibilityRequest, request: Request):
    user = require_user(request)
    db = get_session()
    try:
        folder = get_folder(db, folder_id)
        if not can_manage_folder(folder, user.id, user.is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền thay đổi thư mục này")
        updated = update_folder(db, folder_id, is_public=data.is_public, username=data.username)
        return {"success": True, "is_public": bool(updated.is_public), "username": updated.username}
    finally:
        close_session(db)


@router.delete("/{folder_id}", summary="Xóa thư mục", description="Chỉ chủ sở hữu hoặc admin mới xóa được. File trong thư mục sẽ chuyển về không có thư mục.")
@require_auth
async def delete_folder_endpoint(folder_id: int, request: Request):
    user = require_user(request)
    db = get_session()
    try:
        folder = get_folder(db, folder_id)
        if not can_manage_folder(folder, user.id, user.is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền xóa thư mục này")
        from api.files.repo import File
        db.query(File).filter(File.folder_id == folder_id).update({"folder_id": None})
        db.commit()
        delete_folder(db, folder_id)
        return {"success": True, "message": "Đã xóa thư mục"}
    finally:
        close_session(db)
