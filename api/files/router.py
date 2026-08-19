import os
import tempfile
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, UploadFile, File as FastAPIFile, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.telegram_client import telegram_manager, media_size
from core.streaming import build_media_response
from config.auth import require_user_id, require_user, require_auth
from config.settings import settings
from api.folders.catalog import (
    get_folder, can_access_folder, can_manage_folder, can_access_file,
    can_manage_file, upsert_file, remove_file, list_user_files, list_user_folders,
)
from api.files.repo import Folder, File
from config.database import get_session, close_session
from telethon.tl.types import Channel


def get_file_by_message_id(db: Session, message_id: int) -> Optional[File]:
    return db.query(File).filter(File.message_id == message_id).first()


router = APIRouter(prefix="/api/files", tags=["Telegram Files"])


# Legacy alias for backward compatibility
async def current_client(*args, **kwargs):
    client, _ = await _get_shared_client()
    return client


class FileResponse(BaseModel):
    id: int
    message_id: int
    folder_id: Optional[int]
    name: str
    size: int
    mime_type: Optional[str]
    created_at: str


class RenameFileRequest(BaseModel):
    name: str
    folder_id: Optional[int] = None


class MoveFileRequest(BaseModel):
    target_folder_id: Optional[int]
    source_folder_id: Optional[int] = None


async def _get_shared_client():
    """Get the shared Telegram client (admin's session). Returns (client, user_id)."""
    shared_user_id = telegram_manager._resolve_shared_user_id()
    if shared_user_id is None:
        raise HTTPException(status_code=503, detail="Telegram chưa được kết nối. Vui lòng đăng nhập Telegram lần đầu bằng tài khoản admin.")
    await telegram_manager.ensure_connected(shared_user_id)
    if not telegram_manager.is_connected(shared_user_id):
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối. Vui lòng đăng nhập Telegram bằng tài khoản admin.")
    client = telegram_manager._get_session(shared_user_id).client
    if not client:
        raise HTTPException(status_code=503, detail="Telegram client không khả dụng.")
    return client, shared_user_id


async def get_shared_client():
    """Get only the client for backward compatibility."""
    client, _ = await _get_shared_client()
    return client


async def current_client_with_access(request: Request, want_folder_id: Optional[int] = None):
    """Trả (user, client, folder_info) cho user hiện tại với quyền truy cập đã kiểm tra."""
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        if want_folder_id is not None:
            folder = get_folder(db, want_folder_id)
            if not can_access_folder(folder, user.id, is_superuser):
                raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập thư mục này")
        else:
            folder = None
    finally:
        close_session(db)
    client, _ = await _get_shared_client()
    return user, client, folder


def _doc_name(msg) -> str:
    doc = msg.document
    if not doc:
        return "Photo.jpg" if msg.photo else "Unknown"
    filename = "Unknown"
    if doc.attributes:
        for attr in doc.attributes:
            fn = getattr(attr, "file_name", None)
            if fn:
                filename = fn
                break
    return msg.text.strip() if msg.text and msg.text.strip() else filename


@router.get("", summary="Danh sách file từ DB", description="folder_id=None: file của bạn. folder_id cụ thể: file trong folder đó. Trả về toàn bộ file (không phân trang).")
@require_auth
async def list_files(
    request: Request,
    folder_id: Optional[int] = None,
    search: Optional[str] = None,
):
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        files = list_user_files(db, user.id, is_superuser, folder_id, search)
        folders = list_user_folders(db, user.id, is_superuser)
        folder_map = {fc.id: fc for fc in folders}
        result = []
        for f in files:
            folder = folder_map.get(f.folder_id)
            folder_name = folder.name if folder else ""
            result.append({
                "id": f.message_id,
                "message_id": f.message_id,
                "folder_id": f.folder_id,
                "name": f.name,
                "size": f.size,
                "mime_type": f.mime_type or "application/octet-stream",
                "created_at": f.created_at.isoformat() if f.created_at else "",
                "folder_name": folder_name or "Saved Messages",
                "can_manage": can_manage_file(f, folder, user.id, is_superuser),
                "owner_user_id": f.owner_user_id,
                "uploaded_by_user_id": f.uploaded_by_user_id,
            })
        return {"success": True, "data": result, "count": len(result), "total": len(files), "folder_id": folder_id}
    finally:
        close_session(db)


@router.get("/{message_id}", summary="Chi tiết file")
@require_auth
async def get_file(message_id: int, request: Request, folder_id: Optional[int] = None):
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        file = get_file_by_message_id(db, message_id)
        if not file:
            raise HTTPException(status_code=404, detail="Không tìm thấy file")
        folder = get_folder(db, file.folder_id) if file.folder_id else None
        if not can_access_file(file, folder, user.id, is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập file này")
        return {
            "id": file.message_id,
            "message_id": file.message_id,
            "folder_id": file.folder_id,
            "name": file.name,
            "size": file.size,
            "mime_type": file.mime_type or "application/octet-stream",
            "created_at": file.created_at.isoformat() if file.created_at else "",
        }
    finally:
        close_session(db)


@router.post("", summary="Tải file lên Telegram")
@require_auth
async def upload_file(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    folder_id: Optional[int] = Form(None),
):
    user, client, folder = await current_client_with_access(request, folder_id)
    is_superuser = user.is_superuser
    max_size = settings.MAX_FILE_SIZE
    temp_path = os.path.join(tempfile.gettempdir(), f"td_upload_{file.filename}")

    try:
        size = 0
        with open(temp_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise HTTPException(status_code=413, detail=f"File vượt quá giới hạn {max_size // (1024*1024)} MB")
                f.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="File rỗng")

        peer = await telegram_manager.resolve_peer(user.id, folder_id)
        uploaded = await client.upload_file(temp_path, file_name=file.filename)
        msg = await client.send_file(peer, uploaded, caption="", force_document=True)

        # Determine folder owner for record
        folder_owner = user.id
        if folder:
            folder_owner = folder.owner_user_id
        elif folder_id:
            folder_owner = user.id

        db = get_session()
        try:
            row = upsert_file(
                db,
                owner_user_id=folder_owner,
                uploaded_by_user_id=user.id,
                message_id=msg.id,
                folder_id=folder_id,
                name=file.filename,
                size=size,
                mime_type=file.content_type,
            )
        finally:
            close_session(db)

        return {
            "success": True,
            "data": {
                "id": msg.id,
                "message_id": msg.id,
                "folder_id": folder_id,
                "name": file.filename,
                "size": size,
                "created_at": row.created_at.isoformat() if row and row.created_at else "",
            },
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("/{message_id}/download", summary="Tải file / Stream video")
@require_auth
async def download_file(message_id: int, request: Request, folder_id: Optional[int] = None):
    user = require_user(request)
    is_superuser = user.is_superuser
    db = get_session()
    try:
        file = get_file_by_message_id(db, message_id)
        if not file:
            raise HTTPException(status_code=404, detail="File không tồn tại")
        folder = get_folder(db, file.folder_id) if file.folder_id else None
        if not can_access_file(file, folder, user.id, is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền tải file này")

        client, _ = await _get_shared_client()
        peer = await telegram_manager.resolve_peer(user.id, folder_id)
        msg = await client.get_messages(peer, ids=message_id)
        if not msg or not msg.media:
            raise HTTPException(status_code=404, detail="Không tìm thấy file")

        doc = msg.document
        if not doc:
            raise HTTPException(status_code=400, detail="Tin nhắn không chứa file document")

        filename = file.name
        mime_type = doc.mime_type or "application/octet-stream"
        return build_media_response(request, client, doc, mime_type=mime_type, filename=filename)
    finally:
        close_session(db)


@router.get("/by-message/{message_id}", summary="Chi tiết file theo message_id (dùng cho share links)")
@require_auth
async def get_file_by_msg(message_id: int, request: Request):
    """Get file info for shared link - uses shared client."""
    client, _ = await _get_shared_client()
    me = await client.get_me()
    peer = me
    msg = await client.get_messages(peer, ids=message_id)
    if not msg or not msg.media:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    doc = msg.document
    if not doc:
        raise HTTPException(status_code=400, detail="Không phải file document")
    filename = "Unknown"
    if doc.attributes:
        for attr in doc.attributes:
            fn = getattr(attr, "file_name", None)
            if fn:
                filename = fn
                break
    if msg.text and msg.text.strip():
        filename = msg.text.strip()
    return {
        "message_id": message_id,
        "name": filename,
        "size": doc.size,
        "mime_type": doc.mime_type or "application/octet-stream",
    }


@router.patch("/{message_id}", summary="Đổi tên file")
@require_auth
async def rename_file(message_id: int, data: RenameFileRequest, request: Request):
    user, client, _ = await current_client_with_access(request)
    db = get_session()
    try:
        file = get_file_by_message_id(db, message_id)
        if not file:
            raise HTTPException(status_code=404, detail="File không tồn tại")
        folder = get_folder(db, file.folder_id) if file.folder_id else None
        if not can_access_file(file, folder, user.id, user.is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền đổi tên file này")

        # Try to edit message caption in Telegram
        peer = await telegram_manager.resolve_peer(user.id, data.folder_id)
        try:
            await client.edit_message(peer, message_id, text=data.name)
        except Exception:
            pass

        # Update DB name
        file.name = data.name
        db.commit()
        return {"success": True, "message": f"Đã đổi tên thành {data.name}"}
    finally:
        close_session(db)


@router.post("/{message_id}/move", summary="Di chuyển file")
@require_auth
async def move_file(message_id: int, data: MoveFileRequest, request: Request):
    user, client, target_folder = await current_client_with_access(request, data.target_folder_id)
    is_superuser = user.is_superuser
    db = get_session()

    # Verify source folder access
    source_folder = None
    if data.source_folder_id:
        source_folder = get_folder(db, data.source_folder_id)
        if not can_access_folder(source_folder, user.id, is_superuser):
            raise HTTPException(status_code=403, detail="Bạn không có quyền di chuyển file này")

    if target_folder and not can_manage_folder(target_folder, user.id, is_superuser):
        raise HTTPException(status_code=403, detail="Bạn không có quyền di chuyển vào thư mục này")

    try:
        source_peer = await telegram_manager.resolve_peer(user.id, data.source_folder_id)
        target_peer = await telegram_manager.resolve_peer(user.id, data.target_folder_id)

        fwd = await client.forward_messages(target_peer, message_id, from_peer=source_peer)
        await client.delete_messages(source_peer, [message_id])

        new_msg = fwd[0] if isinstance(fwd, list) else fwd

        # Update DB
        file = get_file_by_message_id(db, message_id)
        if file:
            file.folder_id = data.target_folder_id
            db.commit()

        return {
            "success": True,
            "new_message_id": new_msg.id,
            "message": "Đã di chuyển file thành công",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi di chuyển: {e}")
    finally:
        close_session(db)


@router.delete("/{message_id}", summary="Xóa file")
@require_auth
async def delete_file(message_id: int, request: Request, folder_id: Optional[int] = None):
    user, client, _ = await current_client_with_access(request, folder_id)
    peer = await telegram_manager.resolve_peer(user.id, folder_id)

    try:
        await client.delete_messages(peer, [message_id])
        db = get_session()
        try:
            remove_file(db, message_id)
        finally:
            close_session(db)
        return {"success": True, "message": "Đã xóa file"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xóa file: {e}")