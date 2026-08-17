"""
Core Telegram client manager using Telethon (MTProto).
Each USER has their own TelegramClient + StringSession (per-user drive).
Mirrors the logic of Old_Project auth.rs + utils.rs resolve_peer.
"""
import logging
from typing import Optional, Dict

from sqlalchemy.orm import Session as DbSession
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    ApiIdInvalidError,
    FloodWaitError,
)
from telethon.sessions import StringSession
from telethon.tl.types import Channel

from config.settings import settings
from config.database import get_session, close_session

logger = logging.getLogger(__name__)


# Auth flow states
class AuthState:
    LOGGED_OUT = "logged_out"
    AWAITING_CODE = "awaiting_code"
    AWAITING_PASSWORD = "awaiting_password"
    LOGGED_IN = "logged_in"


class AuthSession:
    """In-memory state for a phone login flow (per user)."""

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.state: str = AuthState.LOGGED_OUT
        self.last_error: Optional[str] = None


class TelegramManager:
    """Manages one TelegramClient per user (per-user drive)."""

    _instance: Optional["TelegramManager"] = None

    def __init__(self):
        # user_id -> AuthSession
        self._sessions: Dict[int, AuthSession] = {}
        # user_id -> client (same reference as session.client)
        self._peer_caches: Dict[int, dict] = {}

    @classmethod
    def get_instance(cls) -> "TelegramManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------- Session / client lifecycle ----------

    def _get_session(self, user_id: int) -> AuthSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = AuthSession()
        return self._sessions[user_id]

    def _load_session_string(self, user_id: int) -> Optional[str]:
        db: Optional[DbSession] = None
        try:
            db = get_session()
            from api.auth.repo import TgSession
            row = db.query(TgSession).filter(TgSession.user_id == user_id).first()
            if row:
                return row.session_string
        except Exception as e:
            logger.warning("Failed to load session for user %s: %s", user_id, e)
        finally:
            close_session(db)
        return None

    def _save_session_string(self, user_id: int, session_string: str):
        db: Optional[DbSession] = None
        try:
            db = get_session()
            from api.auth.repo import TgSession
            row = db.query(TgSession).filter(TgSession.user_id == user_id).first()
            if row:
                row.session_string = session_string
            else:
                db.add(TgSession(user_id=user_id, session_string=session_string))
            db.commit()
        except Exception as e:
            logger.error("Failed to save session for user %s: %s", user_id, e)
        finally:
            close_session(db)

    def _clear_session_string(self, user_id: int):
        db: Optional[DbSession] = None
        try:
            db = get_session()
            from api.auth.repo import TgSession
            row = db.query(TgSession).filter(TgSession.user_id == user_id).first()
            if row:
                db.delete(row)
                db.commit()
        except Exception as e:
            logger.warning("Failed to clear session for user %s: %s", user_id, e)
        finally:
            close_session(db)

    async def get_client(
        self,
        user_id: int,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
    ) -> TelegramClient:
        """Get or create the TelegramClient for a user."""
        api_id = api_id or settings.TELEGRAM_API_ID
        api_hash = api_hash or settings.TELEGRAM_API_HASH

        if not api_id or not api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured")

        sess = self._get_session(user_id)
        if sess.client is not None:
            return sess.client

        session_string = self._load_session_string(user_id)
        session = StringSession(session_string) if session_string else StringSession()

        client = TelegramClient(session, api_id, api_hash, connection_retries=5)
        await client.connect()
        sess.client = client

        if await client.is_user_authorized():
            sess.state = AuthState.LOGGED_IN
            sess.phone = getattr(await client.get_me(), "phone", None)
            self._save_session_string(user_id, session.save())
        else:
            sess.state = AuthState.LOGGED_OUT

        return client

    def _resolve_shared_user_id(self) -> Optional[int]:
        """Return the configured shared telegram user id (admin) if a session exists.
        Falls back to the first superuser with a tg_session row.
        """
        # 1. Explicit config
        if settings.SHARED_TELEGRAM_USER_ID:
            return settings.SHARED_TELEGRAM_USER_ID
        # 2. Find any superuser with a session
        try:
            db = get_session()
            from api.auth.repo import User
            from api.auth.repo import TgSession
            admin = db.query(User).filter(User.is_superuser == True).first()
            if admin:
                sess = db.query(TgSession).filter(TgSession.user_id == admin.id).first()
                if sess:
                    return admin.id
        finally:
            close_session(db)
        return None

    def _effective_user_id(self, user_id: int) -> int:
        """Return the user_id that should be used for all telegram operations.
        If a shared session exists, always use that user id; otherwise fall back to the
        supplied user_id (used during the first admin login before a shared session is set).
        """
        shared = self._resolve_shared_user_id()
        return shared if shared is not None else user_id

    async def ensure_connected(self, user_id: int) -> bool:
        """Restore the shared telegram session (or the user's own if no shared yet)."""
        effective_id = self._effective_user_id(user_id)
        sess = self._get_session(effective_id)
        if sess.state == AuthState.LOGGED_IN:
            return True
        try:
            if not self._load_session_string(effective_id):
                return False
            client = await self.get_client(effective_id)
            if await client.is_user_authorized():
                sess.state = AuthState.LOGGED_IN
                return True
        except Exception as e:
            logger.warning("ensure_connected(user=%s) failed: %s", user_id, e)
        return False

    def is_connected(self, user_id: int) -> bool:
        effective_id = self._effective_user_id(user_id)
        return self._get_session(effective_id).state == AuthState.LOGGED_IN

    def is_authorized(self, user_id: int) -> bool:
        effective_id = self._effective_user_id(user_id)
        return self._get_session(effective_id).state == AuthState.LOGGED_IN

    def auth_state(self, user_id: int) -> str:
        effective_id = self._effective_user_id(user_id)
        return self._get_session(effective_id).state

    def last_error(self, user_id: int) -> Optional[str]:
        effective_id = self._effective_user_id(user_id)
        return self._get_session(effective_id).last_error

    async def get_me(self, user_id: int):
        effective_id = self._effective_user_id(user_id)
        sess = self._get_session(effective_id)
        if not sess.client or sess.state != AuthState.LOGGED_IN:
            return None
        try:
            return await sess.client.get_me()
        except Exception as e:
            logger.warning("get_me(user=%s) failed: %s", user_id, e)
            return None

    # ---------- Auth flow ----------

    async def request_code(
        self, user_id: int, phone: str, api_id: Optional[int] = None, api_hash: Optional[str] = None
    ) -> dict:
        client = await self.get_client(user_id, api_id, api_hash)
        sess = self._get_session(user_id)
        sess.phone = phone
        sess.last_error = None

        try:
            result = await client.send_code_request(phone)
            sess.phone_code_hash = result.phone_code_hash
            sess.state = AuthState.AWAITING_CODE

            delivery = "sms"
            sent_type = getattr(result, "type", None)
            type_str = type(sent_type).__name__.lower() if sent_type else ""
            if "app" in type_str:
                delivery = "telegram_app"
            elif "call" in type_str:
                delivery = "call"
            elif "flash" in type_str:
                delivery = "flash_call"
            elif "email" in type_str:
                delivery = "email"

            return {
                "status": "code_required",
                "delivery": delivery,
                "phone_code_hash": result.phone_code_hash,
                "code_length": getattr(result, "length", 5),
                "resend_after_seconds": getattr(result, "timeout", 60),
            }
        except PhoneNumberInvalidError:
            sess.last_error = "Số điện thoại không hợp lệ."
            raise ValueError("Số điện thoại không hợp lệ. Nhập theo định dạng quốc tế, vd: +84123456789")
        except ApiIdInvalidError:
            sess.last_error = "API ID hoặc API Hash không hợp lệ."
            raise ValueError("API ID hoặc API Hash không hợp lệ.")
        except FloodWaitError as e:
            sess.last_error = f"Vui lòng chờ {e.seconds} giây."
            raise ValueError(f"Quá nhiều yêu cầu. Vui lòng chờ {e.seconds} giây.")
        except Exception as e:
            sess.last_error = str(e)
            raise ValueError(f"Lỗi gửi mã: {e}")

    async def sign_in_code(self, user_id: int, code: str) -> dict:
        sess = self._get_session(user_id)
        if not sess.client or not sess.phone or not sess.phone_code_hash:
            raise ValueError("Chưa có phiên đăng nhập. Hãy gửi mã trước.")

        try:
            try:
                await sess.client.sign_in(
                    sess.phone, code, phone_code_hash=sess.phone_code_hash
                )
            except SessionPasswordNeededError:
                sess.state = AuthState.AWAITING_PASSWORD
                return {"success": False, "next_step": "password", "message": "Tài khoản này cần mật khẩu 2FA."}

            sess.state = AuthState.LOGGED_IN
            self._save_session_string(user_id, sess.client.session.save())
            await self._warm_peer_cache(user_id)
            return {"success": True, "next_step": "dashboard"}
        except PhoneCodeInvalidError:
            raise ValueError("Mã xác thực không đúng. Vui lòng kiểm tra lại.")
        except PhoneCodeExpiredError:
            sess.state = AuthState.LOGGED_OUT
            raise ValueError("Mã đã hết hạn. Vui lòng gửi lại mã.")
        except Exception as e:
            raise ValueError(f"Lỗi xác thực: {e}")

    async def check_password(self, user_id: int, password: str) -> dict:
        sess = self._get_session(user_id)
        if not sess.client or sess.state != AuthState.AWAITING_PASSWORD:
            raise ValueError("Chưa có yêu cầu mật khẩu 2FA.")

        try:
            await sess.client.sign_in(password=password)
            sess.state = AuthState.LOGGED_IN
            self._save_session_string(user_id, sess.client.session.save())
            await self._warm_peer_cache(user_id)
            return {"success": True, "next_step": "dashboard"}
        except Exception as e:
            sess.last_error = str(e)
            raise ValueError(f"Mật khẩu không đúng hoặc lỗi: {e}")

    async def qr_login(
        self, user_id: int, api_id: Optional[int] = None, api_hash: Optional[str] = None
    ) -> str:
        client = await self.get_client(user_id, api_id, api_hash)
        try:
            qr = await client.qr_login()
            sess = self._get_session(user_id)
            sess.state = AuthState.AWAITING_CODE
            return qr.url
        except Exception as e:
            raise ValueError(f"Không thể tạo mã QR: {e}")

    async def qr_poll(self, user_id: int) -> dict:
        sess = self._get_session(user_id)
        if not sess.client:
            return {"success": False, "next_step": "error", "message": "Chưa khởi tạo client."}

        if await sess.client.is_user_authorized():
            sess.state = AuthState.LOGGED_IN
            self._save_session_string(user_id, sess.client.session.save())
            await self._warm_peer_cache(user_id)
            return {"success": True, "next_step": "dashboard"}

        return {"success": False, "next_step": "waiting", "message": "Đợi người dùng quét mã QR."}

    async def logout(self, user_id: int):
        sess = self._get_session(user_id)
        if sess.client:
            try:
                await sess.client.log_out()
            except Exception:
                pass
            try:
                await sess.client.disconnect()
            except Exception:
                pass
        self._sessions.pop(user_id, None)
        self._peer_caches.pop(user_id, None)
        self._clear_session_string(user_id)

    # ---------- Peer resolution ----------

    async def resolve_peer(self, user_id: int, folder_id: Optional[int] = None):
        """Resolve peer for viewing files.
        Folders are now DB-only, so all files are stored in Saved Messages (me).
        folder_id is ignored but kept for interface compatibility."""
        effective_id = self._effective_user_id(user_id)
        sess = self._get_session(effective_id)
        client = sess.client
        if not client or sess.state != AuthState.LOGGED_IN:
            raise ConnectionError("Telegram chưa kết nối")

        # All files are in Saved Messages (the shared user's 'me' entity)
        # folder_id is DB-only, not used for peer resolution
        return await client.get_me()

    async def _warm_peer_cache(self, user_id: int):
        sess = self._get_session(user_id)
        client = sess.client
        if not client or sess.state != AuthState.LOGGED_IN:
            return
        cache = self._peer_caches.setdefault(user_id, {})
        try:
            async for dialog in client.iter_dialogs():
                e = dialog.entity
                if hasattr(e, "id"):
                    cache[getattr(e, "id", 0)] = e
        except Exception as e:
            logger.warning("Warm peer cache failed for user %s: %s", user_id, e)


# ---------- Media helpers (mirror media_size) ----------

def media_size(media) -> int:
    try:
        if isinstance(media, Document) or hasattr(media, "size"):
            size = getattr(media, "size", 0)
            return size if size and size > 0 else 0
        if hasattr(media, "sizes"):
            best = 0
            for size in getattr(media, "sizes", []):
                s = getattr(size, "size", 0)
                if s > best:
                    best = s
            return best
    except Exception:
        pass
    return 0


from telethon.tl.types import Document, Photo  # noqa: E402


# Singleton
telegram_manager = TelegramManager.get_instance()