from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse
from web.templates import templates
from config.auth import get_current_user
from core.telegram_client import telegram_manager

router = APIRouter(prefix="/auth", tags=["Web Auth"])


@router.post("/logout")
async def logout(request: Request):
    resp = RedirectResponse(url="/auth/login", status_code=303)
    resp.delete_cookie("tdrive_token", path="/")
    current_user = get_current_user(request)
    if current_user and current_user.is_active:
        try:
            await telegram_manager.logout(current_user.id)
        except Exception:
            pass
    return resp


@router.get("/login", response_class=_TemplateResponse)
async def login(request: Request):
    current_user = get_current_user(request)
    if current_user and current_user.is_active:
        uid = current_user.id
        await telegram_manager.ensure_connected(uid)
        if telegram_manager.is_connected(uid):
            return RedirectResponse(url="/")
        return RedirectResponse(url="/auth/tg-connect")
    context = {"request": request, "title": "Đăng nhập"}
    return templates.TemplateResponse("auth/login.html", context)


@router.get("/register", response_class=_TemplateResponse)
async def register(request: Request):
    current_user = get_current_user(request)
    if current_user and current_user.is_active:
        return RedirectResponse(url="/")
    context = {"request": request, "title": "Đăng ký"}
    return templates.TemplateResponse("auth/register.html", context)


@router.get("/tg-connect", response_class=_TemplateResponse)
async def tg_connect(request: Request):
    current_user = get_current_user(request)
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/auth/login")
    uid = current_user.id
    await telegram_manager.ensure_connected(uid)
    if telegram_manager.is_connected(uid):
        return RedirectResponse(url="/")
    # Only superuser (admin) can perform Telegram login
    if not current_user.is_superuser:
        return RedirectResponse(url="/")
    context = {"request": request, "title": "Kết nối Telegram"}
    return templates.TemplateResponse("auth/tg_connect.html", context)