"""
User account service: register, login, admin enable/disable.
Users are stored in PostgreSQL. New registrations are DISABLED by default
and must be enabled by an admin before they can log in.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from api.auth.repo import User
from config.settings import settings

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "is_superuser": user.is_superuser,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def register_user(db: Session, email: str, password: str, full_name: Optional[str] = None, ip: Optional[str] = None) -> tuple[User, str]:
    """Create a new user. Returns (user, status).
    status: 'disabled' (awaiting admin) | 'exists'
    """
    email = email.lower().strip()
    existing = get_user_by_email(db, email)
    if existing:
        return existing, "exists"

    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_active=False,      # DISABLED by default - must be enabled by admin
        is_superuser=False,
        registered_ip=ip,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, "disabled"


def count_users_by_ip(db: Session, ip: str) -> int:
    """Đếm số tài khoản (cả active & inactive) được tạo từ cùng một IP."""
    if not ip:
        return 0
    return db.query(User).filter(User.registered_ip == ip).count()


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Login. Returns None if credentials wrong, or if account is disabled,
    or raises a ValueError if account exists but is disabled."""
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.id.asc()).all()


def set_user_active(db: Session, user_id: int, active: bool) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.is_active = bool(active)
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, user_id: int, new_password: str) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


def change_own_password(db: Session, user: User, current_password: str, new_password: str) -> bool:
    if not verify_password(current_password, user.hashed_password):
        return False
    user.hashed_password = hash_password(new_password)
    db.commit()
    return True


def bootstrap_initial_admin(db: Session) -> Optional[User]:
    """Create the first admin account from .env settings if the users table is empty."""
    email = settings.INITIAL_ADMIN_EMAIL
    password = settings.INITIAL_ADMIN_PASSWORD
    if not email or not password:
        return None

    count = db.query(User).count()
    if count > 0:
        return None

    admin = User(
        email=email.lower().strip(),
        full_name="Administrator",
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Created initial admin account: %s", admin.email)
    return admin