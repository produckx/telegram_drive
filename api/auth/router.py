from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Optional, List

from api.auth.schema import LoginRequest, LoginResponse, RegisterRequest, UserOut, AdminUpdateRequest, ResetPasswordRequest, ChangePasswordRequest
from api.auth import service as user_service
from api.auth.repo import User
from config.database import get_session, close_session
from config.auth import require_user, require_superuser, require_user_id
from config.settings import settings
from config.rate_limit import login_guard, get_client_ip
from core.telegram_client import telegram_manager

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ============================ USER ACCOUNT ============================

@router.post("/register", summary="Đăng ký tài khoản", description="Tạo tài khoản mới. Mặc định bị DISABLE, phải được admin kích hoạt mới đăng nhập được. Mỗi IP công cộng tối đa 50 tài khoản.")
async def register(data: RegisterRequest, request: Request):
    ip = get_client_ip(request)
    db = get_session()
    try:
        # Giới hạn số tài khoản trên mỗi IP công cộng
        if user_service.count_users_by_ip(db, ip) >= settings.MAX_ACCOUNTS_PER_IP:
            raise HTTPException(
                status_code=429,
                detail=f"IP của bạn đã đạt giới hạn {settings.MAX_ACCOUNTS_PER_IP} tài khoản. Vui lòng liên hệ quản trị viên.",
            )
        user, status = user_service.register_user(db, data.email, data.password, data.full_name, ip=ip)
        if status == "exists":
            raise HTTPException(status_code=409, detail="Email đã được đăng ký")
        return {
            "success": True,
            "message": "Đăng ký thành công! Tài khoản của bạn cần được quản trị viên kích hoạt trước khi đăng nhập.",
            "data": UserOut.model_validate(user),
        }
    finally:
        close_session(db)


@router.post("/login", response_model=LoginResponse, summary="Đăng nhập tài khoản", description="Đăng nhập bằng email/mật khẩu. Tài khoản chưa được kích hoạt sẽ bị từ chối. Có bảo vệ chống dò mật khẩu (5 lần sai sẽ bị khóa 15 phút).")
async def login(data: LoginRequest, request: Request, response: Response):
    ip = get_client_ip(request)
    email_key = f"{ip}:{data.email.lower().strip()}"

    # Chống brute-force: khóa tạm thời nếu đăng nhập sai quá nhiều lần
    if login_guard.is_blocked(email_key):
        retry = login_guard.retry_after(email_key)
        raise HTTPException(
            status_code=429,
            detail=f"Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau {retry} giây.",
        )

    db = get_session()
    try:
        user = user_service.authenticate_user(db, data.email, data.password)
        if not user:
            login_guard.record_failure(email_key)
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Tài khoản chưa được kích hoạt. Vui lòng liên hệ quản trị viên.",
            )

        login_guard.clear(email_key)
        token = user_service.create_access_token(user)

        # Set cookie for web pages
        response.set_cookie(
            key="tdrive_token",
            value=token,
            max_age=60 * 60 * 24 * 7,
            httponly=True,
            samesite="lax",
        )

        return LoginResponse(
            access_token=token,
            token_type="bearer",
            expires_in=60 * 60 * 24 * 7,
            user=UserOut.model_validate(user).model_dump(),
        )
    finally:
        close_session(db)


@router.get("/me", summary="Thông tin tài khoản hiện tại", description="Xem thông tin tài khoản đang đăng nhập.")
def me(request: Request):
    user = require_user(request)
    return {"success": True, "data": UserOut.model_validate(user)}


@router.get("/users", response_model=List[UserOut], summary="Danh sách tài khoản (admin)", description="Admin xem danh sách tài khoản để duyệt/kích hoạt.")
def list_users(request: Request):
    require_superuser(request)
    db = get_session()
    try:
        users = user_service.list_users(db)
        return [UserOut.model_validate(u) for u in users]
    finally:
        close_session(db)


@router.patch("/users/{user_id}", response_model=UserOut, summary="Cập nhật tài khoản (admin)", description="Admin kích hoạt / vô hiệu hóa tài khoản, hoặc nâng quyền admin.")
def update_user(user_id: int, data: AdminUpdateRequest, request: Request):
    admin = require_superuser(request)
    db = get_session()
    try:
        user = user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

        if data.active is not None:
            user.is_active = bool(data.active)
        if data.superuser is not None:
            user.is_superuser = bool(data.superuser)

        db.commit()
        db.refresh(user)
        return UserOut.model_validate(user)
    finally:
        close_session(db)


@router.post("/logout", summary="Đăng xuất (tài khoản + Telegram)")
async def logout(request: Request, response: Response):
    response.delete_cookie("tdrive_token")
    from config.auth import get_current_user
    current_user = get_current_user(request)
    if current_user and current_user.is_active:
        try:
            await telegram_manager.logout(current_user.id)
        except Exception:
            pass
    return {"success": True, "message": "Đã đăng xuất"}


@router.post("/users/{user_id}/reset-password", summary="Đặt lại mật khẩu (admin)", description="Admin đặt lại mật khẩu mới cho user.")
def reset_user_password(user_id: int, data: ResetPasswordRequest, request: Request):
    require_superuser(request)
    db = get_session()
    try:
        user = user_service.reset_password(db, user_id, data.new_password)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
        return {"success": True, "message": f"Đã đặt lại mật khẩu cho {user.email}"}
    finally:
        close_session(db)


@router.post("/change-password", summary="Đổi mật khẩu của chính mình", description="Người dùng tự đổi mật khẩu (cần nhập mật khẩu hiện tại).")
def change_own_password(data: ChangePasswordRequest, request: Request):
    user = require_user(request)
    db = get_session()
    try:
        ok = user_service.change_own_password(db, user, data.current_password, data.new_password)
        if not ok:
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
        return {"success": True, "message": "Đã đổi mật khẩu thành công"}
    finally:
        close_session(db)


# ============================ TELEGRAM CONNECT ============================

class SendCodeRequest(BaseModel):
    phone: str
    api_id: Optional[int] = None
    api_hash: Optional[str] = None


class SignInRequest(BaseModel):
    code: str


class PasswordRequest(BaseModel):
    password: str


class QrLoginRequest(BaseModel):
    api_id: Optional[int] = None
    api_hash: Optional[str] = None


@router.post("/send-code", summary="Gửi mã xác thực Telegram", description="Sau khi đăng nhập tài khoản, gửi mã OTP đến số điện thoại Telegram để kết nối.")
async def send_code(data: SendCodeRequest, request: Request):
    user = require_user(request)
    try:
        res = await telegram_manager.request_code(user.id, data.phone, data.api_id, data.api_hash)
        return {"success": True, "data": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định: {e}")


@router.post("/sign-in", summary="Xác thực mã OTP", description="Nhập mã OTP từ Telegram để kết nối.")
async def sign_in(data: SignInRequest, request: Request):
    user = require_user(request)
    try:
        res = await telegram_manager.sign_in_code(user.id, data.code)
        return {"success": True, "data": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xác thực: {e}")


@router.post("/check-password", summary="Xác thực mật khẩu 2FA", description="Nhập mật khẩu đám mây (2FA) nếu tài khoản Telegram bật xác thực 2 lớp.")
async def check_password(data: PasswordRequest, request: Request):
    user = require_user(request)
    try:
        res = await telegram_manager.check_password(user.id, data.password)
        return {"success": True, "data": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi mật khẩu 2FA: {e}")


@router.post("/qr/start", summary="Bắt đầu đăng nhập bằng QR", description="Tạo URL mã QR (tg://login?token=...) để quét trên app Telegram.")
async def qr_start(data: QrLoginRequest, request: Request):
    user = require_user(request)
    try:
        url = await telegram_manager.qr_login(user.id, data.api_id, data.api_hash)
        return {"success": True, "data": {"url": url}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo QR: {e}")


@router.get("/qr/poll", summary="Kiểm tra trạng thái quét mã QR", description="Poll kiểm tra xem người dùng đã quét mã QR trên điện thoại chưa.")
async def qr_poll(request: Request):
    user = require_user(request)
    try:
        res = await telegram_manager.qr_poll(user.id)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", summary="Trạng thái tài khoản + kết nối Telegram", description="Kiểm tra tài khoản hiện tại và trạng thái kết nối Telegram.")
async def auth_status(request: Request):
    from config.auth import get_current_user
    current_user = None
    try:
        current_user = get_current_user(request)
    except Exception:
        current_user = None

    if current_user and current_user.is_active:
        await telegram_manager.ensure_connected(current_user.id)
        is_connected = telegram_manager.is_connected(current_user.id)
        is_auth = telegram_manager.is_authorized(current_user.id)
        tg_user = None
        if is_auth:
            me = await telegram_manager.get_me(current_user.id)
            if me:
                tg_user = {
                    "id": me.id,
                    "first_name": getattr(me, "first_name", ""),
                    "last_name": getattr(me, "last_name", ""),
                    "username": getattr(me, "username", ""),
                    "phone": getattr(me, "phone", ""),
                }
        return {
            "success": True,
            "logged_in": True,
            "user": UserOut.model_validate(current_user).model_dump(),
            "tg_connected": is_connected,
            "tg_authorized": is_auth,
            "auth_state": telegram_manager.auth_state(current_user.id),
            "tg_user": tg_user,
        }

    return {
        "success": True,
        "logged_in": False,
        "user": None,
        "tg_connected": False,
        "tg_authorized": False,
        "auth_state": "logged_out",
        "tg_user": None,
    }