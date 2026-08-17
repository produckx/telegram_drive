from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from config.auth import get_current_user
from api.auth import service as user_service
from config.database import get_session, close_session

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_class=_TemplateResponse)
async def users(request: Request):
    current_user = get_current_user(request)
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/auth/login")
    if not current_user.is_superuser:
        return RedirectResponse(url="/")

    db = get_session()
    try:
        user_list = user_service.list_users(db)
        context = {
            "request": request,
            "title": "Quản lý tài khoản",
            "users": user_list,
        }
        return templates.TemplateResponse("admin/users.html", context)
    finally:
        close_session(db)