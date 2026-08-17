import os
import time
import secrets
import hashlib
import bcrypt
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from config.database import get_session, close_session
from config.auth import require_user
from api.files.repo import SharedLink
from core.telegram_client import telegram_manager
from core.streaming import build_media_response

router = APIRouter(tags=["Share Links"])


class CreateShareRequest(BaseModel):
    message_id: int
    folder_id: Optional[int] = None
    file_name: str
    file_size: int = 0
    password: Optional[str] = None
    expires_in_hours: Optional[int] = None


def generate_cookie_token(token: str, password_hash: str) -> str:
    return hashlib.sha256(f"{token}:{password_hash}".encode()).hexdigest()


@router.post("/api/shares", summary="Tạo link chia sẻ file", description="Tạo một đường link công khai (có thể đặt mật khẩu hoặc hạn dùng) để chia sẻ file trực tiếp.")
async def create_share_link(data: CreateShareRequest, request: Request):
    user = require_user(request)
    db = get_session()
    try:
        token = secrets.token_hex(16)
        password_hash = None
        if data.password and data.password.strip():
            password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt(12)).decode()

        expires_at = None
        if data.expires_in_hours and data.expires_in_hours > 0:
            expires_at = int(time.time()) + (data.expires_in_hours * 3600)

        record = SharedLink(
            id=token,
            user_id=user.id,
            folder_id=data.folder_id,
            message_id=data.message_id,
            file_name=data.file_name,
            file_size=data.file_size,
            password_hash=password_hash,
            expires_at=expires_at,
            created_at=int(time.time()),
        )
        db.add(record)
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        share_url = f"{base_url}/d/{token}"

        return {
            "success": True,
            "token": token,
            "share_url": share_url,
            "expires_at": expires_at,
            "has_password": password_hash is not None,
        }
    finally:
        close_session(db)


@router.get("/d/{token}", summary="Xem / Tải file chia sẻ", description="Trang chia sẻ file công khai. Nếu có mật khẩu sẽ hiện form nhập.")
async def view_shared_file(token: str, request: Request):
    db = get_session()
    try:
        record = db.query(SharedLink).filter(SharedLink.id == token).first()
        if not record or record.revoked:
            raise HTTPException(status_code=404, detail="File không tồn tại hoặc link chia sẻ đã bị thu hồi.")

        if record.expires_at and record.expires_at < int(time.time()):
            raise HTTPException(status_code=410, detail="Đường link chia sẻ đã hết hạn.")

        # Check password
        if record.password_hash:
            cookie_val = request.cookies.get(f"share_auth_{token}")
            expected = generate_cookie_token(token, record.password_hash)
            if cookie_val != expected:
                # Render password form
                html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><title>File được bảo vệ</title>
    <link rel="stylesheet" href="/static/vendor/bootstrap/bootstrap.min.css">
    <link rel="stylesheet" href="/static/css/app.css">
</head>
<body class="d-flex align-items-center justify-content-center" style="min-height:100vh;">
    <div class="card p-4" style="max-width:400px; width:100%;">
        <h4 class="mb-3 text-center">File được bảo vệ bằng mật khẩu</h4>
        <p class="text-muted text-center">{record.file_name}</p>
        <form method="post" action="/d/{token}/verify">
            <div class="mb-3">
                <input type="password" name="password" class="form-control" placeholder="Nhập mật khẩu để tải" required autofocus>
            </div>
            <button type="submit" class="btn btn-primary w-100">Mở khóa và Tải</button>
        </form>
    </div>
</body>
</html>"""
                return HTMLResponse(content=html)

        # Stream directly from owner's Telegram
        owner_id = int(record.user_id or 0)
        ok = await telegram_manager.ensure_connected(owner_id)
        if not ok or not telegram_manager.is_connected(owner_id):
            raise HTTPException(status_code=503, detail="Chủ file chưa sẵn sàng (Telegram chưa kết nối)")
        client = telegram_manager._get_session(owner_id).client

        peer = await telegram_manager.resolve_peer(owner_id, record.folder_id)
        msg = await client.get_messages(peer, ids=record.message_id)
        if not msg or not msg.document:
            raise HTTPException(status_code=404, detail="File không còn tồn tại trên Telegram")

        doc = msg.document
        mime = doc.mime_type or "application/octet-stream"
        return build_media_response(request, client, doc, mime_type=mime, filename=record.file_name)
    finally:
        close_session(db)


@router.post("/d/{token}/verify", summary="Xác thực mật khẩu file chia sẻ")
async def verify_share_password(token: str, password: str = Form(...)):
    db = get_session()
    try:
        record = db.query(SharedLink).filter(SharedLink.id == token).first()
        if not record or not record.password_hash:
            raise HTTPException(status_code=400, detail="Không yêu cầu mật khẩu")

        if not bcrypt.checkpw(password.encode(), record.password_hash.encode()):
            return HTMLResponse(
                f"<div class='alert alert-danger'>Mật khẩu không đúng. <a href='/d/{token}'>Thử lại</a></div>",
                status_code=401,
            )

        cookie_val = generate_cookie_token(token, record.password_hash)
        resp = RedirectResponse(url=f"/d/{token}", status_code=303)
        resp.set_cookie(
            key=f"share_auth_{token}",
            value=cookie_val,
            max_age=1800,
            httponly=True,
            samesite="lax",
        )
        return resp
    finally:
        close_session(db)