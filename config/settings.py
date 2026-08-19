from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import field_validator


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "Telegram Drive API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    MODE: str = "development"  # development, production

    # Database
    DATABASE_URL: str = "postgresql://irv:Inoue%402025@localhost:5432/drive"
    DATABASE_ECHO: bool = False

    # Auth
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 ngày
    API_KEY: str = "tdrive-api-key-2024"  # For API authentication
    # Admin bootstrap: tạo tài khoản admin đầu tiên nếu bảng users rỗng
    INITIAL_ADMIN_EMAIL: Optional[str] = None
    INITIAL_ADMIN_PASSWORD: Optional[str] = None

    # Shared Telegram account: chỉ admin đăng nhập Telegram, các user khác dùng chung session
    SHARED_TELEGRAM_USER_ID: Optional[int] = None

    # File upload
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 2_000_000_000  # 2GB
    ALLOWED_EXTENSIONS: str = "*"

    # Telegram (provided by user via .env)
    TELEGRAM_API_ID: Optional[int] = None
    TELEGRAM_API_HASH: Optional[str] = None
    # Telethon session name (base64 StringSession stored in DB)
    TELEGRAM_SESSION_NAME: str = "tdrive_session"
    # Max file size for Telegram upload (2 GiB limit)
    TELEGRAM_MAX_FILE_SIZE: int = 2_147_483_648
    # Chunk sizes
    MT_PROTO_CHUNK_SIZE: int = 65536
    CDN_ALIGNMENT: int = 524288

    # WebDAV
    WEBDAV_ENABLED: bool = True
    WEBDAV_PORT: int = 14202
    WEBDAV_HOST: str = "127.0.0.1"
    WEBDAV_READ_ONLY: bool = True

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # Account/registration limits
    MAX_ACCOUNTS_PER_IP: int = 50  # mỗi IP công cộng chỉ được tối đa 50 tài khoản đăng ký

    # Rate limits: giới hạn SỐ LẦN GỌI API (không phải giới hạn số item trả về)
    RATE_LIMIT_PER_ACCOUNT: int = 20      # 20 request/giây/account (chưa đăng nhập thì tính theo IP)
    RATE_LIMIT_ACCOUNT_WINDOW: int = 1    # window 1 giây

    @field_validator("TELEGRAM_API_ID", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        if v in (None, ""):
            return None
        return v


settings = AppSettings()