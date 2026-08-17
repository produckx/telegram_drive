from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from api.folders.repo import Folder
from api.folders.schema import FolderCreate, FolderUpdate


def create_folder(db: Session, data: FolderCreate) -> Optional[Folder]:
    folder = Folder(
        name=data.name,
        parent_id=data.parent_id,
        username=data.username,
    )
    db.add(folder)
    try:
        db.commit()
        db.refresh(folder)
        return folder
    except Exception:
        db.rollback()
        return None


def get_folder(db: Session, folder_id: int) -> Optional[Folder]:
    return db.query(Folder).filter(Folder.id == folder_id).first()


def list_folders(db: Session, parent_id: Optional[int] = None) -> List[Folder]:
    query = db.query(Folder)
    if parent_id is not None:
        query = query.filter(Folder.parent_id == parent_id)
    else:
        query = query.filter(Folder.parent_id.is_(None))
    return query.order_by(Folder.display_order, Folder.name).all()


def update_folder(db: Session, folder_id: int, data: FolderUpdate) -> Optional[Folder]:
    folder = get_folder(db, folder_id)
    if not folder:
        return None

    if data.name is not None:
        folder.name = data.name
    if data.username is not None:
        folder.username = data.username
    if data.is_public is not None:
        folder.is_public = data.is_public

    try:
        db.commit()
        db.refresh(folder)
        return folder
    except Exception:
        db.rollback()
        return None


def delete_folder(db: Session, folder_id: int) -> bool:
    folder = get_folder(db, folder_id)
    if not folder:
        return False

    try:
        db.delete(folder)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def get_empty_folders(db: Session) -> List[Folder]:
    """Get folders that have no files."""
    subquery = db.query(Folder.id).filter(Folder.id == Folder.id).subquery()
    return (
        db.query(Folder)
        .filter(
            ~Folder.id.in_(db.query(Folder.id).join(Folder.files)),
            Folder.parent_id.isnot(None),
        )
        .all()
    )