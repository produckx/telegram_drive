from fastapi import Request, HTTPException
from functools import wraps
from typing import Optional
from sqlalchemy.orm import Session

from config.settings import settings
from config.database import get_session, close_session
from api.auth.service import decode_access_token, get_user_by_id
from api.auth.repo import User


def verify_api_key(request: Request):
    """Verify API key from request headers."""
    x_api_key = request.headers.get("x-api-key")
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return x_api_key


def resolve_auth(func):
    """Decorator: set __auth_required__ + auto-call verify_api_key(request)."""
    func.__auth_required__ = True

    @wraps(func)
    def wrapper(*args, **kwargs):
        request = kwargs.get("request")
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if request is not None:
            verify_api_key(request)
        return func(*args, **kwargs)

    return wrapper


def require_auth(func):
    """Decorator: set __auth_required__ để Swagger UI hiển thị ổ khóa tự động.

    Usage:
    @router.get("/me")
    @require_auth
    def me(request: Request):
        user = require_user(request)  # ...
    """
    func.__auth_required__ = True
    return func


def get_current_user(request: Request) -> Optional[User]:
    """Lấy user hiện tại từ JWT (Authorization Bearer hoặc cookie 'tdrive_token').
    Trả None nếu không có/sai token, hoặc user không còn active."""
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("tdrive_token")
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    try:
        user_id = int(payload.get("sub", "0"))
    except (TypeError, ValueError):
        return None

    db: Optional[Session] = None
    try:
        db = get_session()
        user = get_user_by_id(db, user_id)
        if not user or not user.is_active:
            return None
        return user
    finally:
        close_session(db)


def require_user(request: Request) -> User:
    """Like get_current_user but raises 401/403 when not allowed."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản bị vô hiệu hóa")
    return user


def require_superuser(request: Request) -> User:
    user = require_user(request)
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Yêu cầu quyền admin")
    return user


def require_user_id(request: Request) -> int:
    """Lấy user_id hiện tại hoặc ném 401."""
    user = require_user(request)
    return user.id