"""
Catalog service: DB-driven folder & file ownership/visibility.
Architecture:
- Files are stored in a single shared Telegram account (Saved Messages).
- Folders and file metadata are stored in PostgreSQL for per-user access control.
- Access rules:
    * User sees: own folders/files + public folders/files of other users
    * Admin (superuser) sees: everything
"""
import re
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session, Query

from api.files.repo import Folder, File


def clean_folder_name(raw_title: str) -> str:
    """Strip [TD] or [td] from channel title."""
    return re.sub(r"\s*\[td\]\s*", "", raw_title or "", flags=re.IGNORECASE).strip()


def create_folder(
    db: Session,
    owner_user_id: int,
    name: str,
    is_public: bool = False,
    username: Optional[str] = None,
) -> Folder:
    """Create a new DB-only folder (no Telegram channel created)."""
    folder = Folder(
        owner_user_id=owner_user_id,
        name=name,
        username=username,
        is_public=1 if is_public else 0,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def update_folder(db: Session, folder_id: int, name: str = None, is_public: bool = None, username: str = None) -> Optional[Folder]:
    """Update folder name, visibility, or username."""
    folder = get_folder(db, folder_id)
    if not folder:
        return None
    if name is not None:
        folder.name = name
    if is_public is not None:
        folder.is_public = 1 if is_public else 0
    if username is not None:
        folder.username = username
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, folder_id: int) -> bool:
    """Delete folder and optionally its files from Telegram."""
    folder = get_folder(db, folder_id)
    if not folder:
        return False
    db.delete(folder)
    db.commit()
    return True


def get_folder(db: Session, folder_id: int) -> Optional[Folder]:
    return db.query(Folder).filter(Folder.id == folder_id).first()


def get_file_by_message_id(db: Session, message_id: int) -> Optional[File]:
    return db.query(File).filter(File.message_id == message_id).first()


def can_manage_file(file: Optional[File], folder: Optional[Folder], user_id: int, is_superuser: bool) -> bool:
    """Check if user can delete/rename/move the file."""
    if file is None:
        return False
    if is_superuser:
        return True
    if file.owner_user_id == user_id:
        return True
    if file.uploaded_by_user_id == user_id:
        return True
    if folder and folder.owner_user_id == user_id:
        return True
    return False


def can_access_folder(folder: Optional[Folder], user_id: int, is_superuser: bool) -> bool:
    """Check if user can view this folder."""
    if folder is None:
        return False
    if is_superuser:
        return True
    if folder.owner_user_id == user_id:
        return True
    if folder.is_public:
        return True
    return False


def can_manage_folder(folder: Optional[Folder], user_id: int, is_superuser: bool) -> bool:
    """Check if user can manage (edit/upload/delete) this folder."""
    if folder is None:
        return False
    if is_superuser:
        return True
    return folder.owner_user_id == user_id


def can_access_file(file: Optional[File], folder: Optional[Folder], user_id: int, is_superuser: bool) -> bool:
    """Check if user can access/download this file."""
    if is_superuser:
        return True
    if file and file.owner_user_id == user_id:
        return True
    if folder and can_access_folder(folder, user_id, is_superuser):
        return True
    return False


def list_user_folders(db: Session, user_id: int, is_superuser: bool) -> List[Folder]:
    """List folders user can see: own + public (+ all if admin)."""
    if is_superuser:
        return db.query(Folder).order_by(Folder.name.asc()).all()
    return (
        db.query(Folder)
        .filter((Folder.owner_user_id == user_id) | (Folder.is_public == 1))
        .order_by(Folder.name.asc())
        .all()
    )


def list_user_files(
    db: Session,
    user_id: int,
    is_superuser: bool,
    folder_id: Optional[int] = None,
    search: Optional[str] = None,
) -> List[File]:
    """List files user can access with proper access control."""
    q: Query = db.query(File)
    if is_superuser:
        if folder_id is not None:
            q = q.filter(File.folder_id == folder_id)
        if search:
            q = q.filter(File.name.ilike(f"%{search}%"))
    else:
        # User sees: their files + files in their folders + public folder files
        if folder_id is not None:
            folder = get_folder(db, folder_id)
            if not folder or (folder.owner_user_id != user_id and not folder.is_public):
                return []
            q = q.filter(File.folder_id == folder_id)
        else:
            # Get accessible folder IDs
            folder_ids = [f.id for f in db.query(Folder.id).filter(
                (Folder.owner_user_id == user_id) | (Folder.is_public == 1)
            ).all()]
            q = q.filter(
                (File.owner_user_id == user_id) |
                (File.uploaded_by_user_id == user_id) |
                (File.folder_id.in_(folder_ids))
            )
        if search:
            q = q.filter(File.name.ilike(f"%{search}%"))
    return q.order_by(File.created_at.desc()).all()


def count_folder_files(db: Session, folder_id: int) -> int:
    """Count files in a specific folder."""
    return db.query(File).filter(File.folder_id == folder_id).count()


def upsert_file(
    db: Session,
    owner_user_id: int,
    uploaded_by_user_id: int,
    message_id: int,
    folder_id: Optional[int],
    name: str,
    size: int,
    mime_type: Optional[str] = None,
) -> File:
    """Record a file in the catalog (uploaded)."""
    row = db.query(File).filter(File.message_id == message_id).first()
    if not row:
        row = File(
            owner_user_id=owner_user_id,
            uploaded_by_user_id=uploaded_by_user_id,
            message_id=message_id,
            folder_id=folder_id,
            name=name,
            size=size,
            mime_type=mime_type,
            file_ext=name.rsplit(".", 1)[-1].lower() if "." in name else None,
        )
        db.add(row)
    else:
        row.owner_user_id = owner_user_id
        row.uploaded_by_user_id = uploaded_by_user_id
        row.folder_id = folder_id
        row.name = name
        row.size = size
        row.mime_type = mime_type
        row.file_ext = name.rsplit(".", 1)[-1].lower() if "." in name else None
    db.commit()
    db.refresh(row)
    return row


def remove_file(db: Session, message_id: int):
    row = db.query(File).filter(File.message_id == message_id).first()
    if row:
        db.delete(row)
        db.commit()


def folder_to_dict(folder: Folder, user_id: int = None, is_superuser: bool = False) -> dict:
    is_owner = is_superuser or (folder.owner_user_id == user_id) if user_id is not None else False
    return {
        "id": folder.id,
        "owner_user_id": folder.owner_user_id,
        "name": folder.name,
        "username": folder.username,
        "is_public": bool(folder.is_public),
        "is_owner": is_owner,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
    }