from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List
from datetime import datetime

from api.files.repo import File, Folder, EncryptedFile
from api.files.schema import FileCreate, FileUpdate, BulkActionRequest


def create_file(db: Session, data: FileCreate) -> Optional[File]:
    file = File(
        message_id=data.message_id,
        folder_id=data.folder_id,
        name=data.name,
        size=data.size,
        mime_type=data.mime_type,
    )
    db.add(file)
    try:
        db.commit()
        db.refresh(file)
        return file
    except Exception:
        db.rollback()
        return None


def get_file(db: Session, message_id: int, folder_id: Optional[int] = None) -> Optional[File]:
    query = db.query(File).filter(File.message_id == message_id)
    if folder_id is not None:
        query = query.filter(File.folder_id == folder_id)
    return query.first()


def list_files(
    db: Session,
    folder_id: Optional[int] = None,
    search: Optional[str] = None,
    mime_type: Optional[str] = None,
    size_min: Optional[int] = None,
    size_max: Optional[int] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> tuple[List[File], int]:
    query = db.query(File)

    if folder_id is not None:
        query = query.filter(File.folder_id == folder_id)

    if search:
        query = query.filter(File.name.ilike(f"%{search}%"))

    if mime_type:
        query = query.filter(File.mime_type.ilike(f"%{mime_type}%"))

    if size_min is not None:
        query = query.filter(File.size >= size_min)

    if size_max is not None:
        query = query.filter(File.size <= size_max)

    # Sorting
    sort_column = getattr(File, sort, File.created_at)
    if order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    total = query.count()

    offset = (page - 1) * limit
    files = query.offset(offset).limit(limit).all()

    return files, total


def update_file(db: Session, message_id: int, data: FileUpdate, folder_id: Optional[int] = None) -> Optional[File]:
    file = get_file(db, message_id, folder_id)
    if not file:
        return None

    if data.name is not None:
        file.name = data.name
    if data.folder_id is not None:
        file.folder_id = data.folder_id
    file.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(file)
        return file
    except Exception:
        db.rollback()
        return None


def delete_file(db: Session, message_id: int, folder_id: Optional[int] = None) -> bool:
    file = get_file(db, message_id, folder_id)
    if not file:
        return False

    try:
        db.delete(file)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def copy_file(db: Session, message_id: int, target_folder_id: int, source_folder_id: Optional[int] = None) -> Optional[File]:
    source_file = get_file(db, message_id, source_folder_id)
    if not source_file:
        return None

    new_file = File(
        message_id=message_id,  # In real scenario, this would be a new message ID
        folder_id=target_folder_id,
        name=source_file.name,
        size=source_file.size,
        mime_type=source_file.mime_type,
    )
    db.add(new_file)
    try:
        db.commit()
        db.refresh(new_file)
        return new_file
    except Exception:
        db.rollback()
        return None


def bulk_action(db: Session, data: BulkActionRequest) -> int:
    count = 0
    for file_id in data.file_ids:
        if data.action == "delete":
            if delete_file(db, file_id, data.folder_id):
                count += 1
        elif data.action == "move" and data.payload and "folder_id" in data.payload:
            if update_file(db, file_id, FileUpdate(folder_id=data.payload["folder_id"]), data.folder_id):
                count += 1
        # archive would be handled differently
    return count


def search_files(
    db: Session,
    query: str,
    folder_id: Optional[int] = None,
    limit: int = 20,
) -> List[File]:
    q = db.query(File).filter(File.name.ilike(f"%{query}%"))
    if folder_id is not None:
        q = q.filter(File.folder_id == folder_id)
    return q.limit(limit).all()


def is_encrypted(db: Session, folder_key: str, message_id: int) -> bool:
    return (
        db.query(EncryptedFile)
        .filter(
            EncryptedFile.folder_key == folder_key,
            EncryptedFile.message_id == message_id,
            EncryptedFile.record_state == "active",
        )
        .first()
        is not None
    )