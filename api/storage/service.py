from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict

from api.files.repo import File, Folder


def get_storage_stats(db: Session) -> Dict:
    """Aggregate storage statistics."""
    total_result = (
        db.query(
            func.count(File.id),
            func.coalesce(func.sum(File.size), 0),
        ).first()
    )
    total_file_count = total_result[0] or 0
    total_size = total_result[1] or 0

    # Per-folder stats
    folder_stats = (
        db.query(
            File.folder_id,
            Folder.name,
            func.count(File.id),
            func.coalesce(func.sum(File.size), 0),
        )
        .join(Folder, Folder.id == File.folder_id)
        .group_by(File.folder_id, Folder.name)
        .all()
    )

    folders = [
        {
            "id": fid,
            "name": name,
            "file_count": count,
            "size_bytes": size,
        }
        for fid, name, count, size in folder_stats
    ]

    # MIME type stats
    mime_stats = (
        db.query(
            File.mime_type,
            func.count(File.id),
            func.coalesce(func.sum(File.size), 0),
        )
        .group_by(File.mime_type)
        .all()
    )

    mime_types = [
        {
            "mime_type": mime_type or "application/octet-stream",
            "file_count": count,
            "size_bytes": size,
        }
        for mime_type, count, size in mime_stats
    ]

    return {
        "total_storage_used_bytes": total_size,
        "total_file_count": total_file_count,
        "folders": folders,
        "mime_types": mime_types,
    }


def get_duplicates(db: Session) -> List[Dict]:
    """Find files with identical name and size."""
    subquery = (
        db.query(File.name, File.size, func.count(File.id).label("cnt"))
        .group_by(File.name, File.size)
        .having(func.count(File.id) > 1)
        .subquery()
    )

    results = (
        db.query(File)
        .join(subquery, (File.name == subquery.c.name) & (File.size == subquery.c.size))
        .order_by(File.name, File.size)
        .all()
    )

    groups: Dict[tuple, List[File]] = {}
    for f in results:
        key = (f.name, f.size)
        groups.setdefault(key, []).append(f)

    return [
        {
            "name": name,
            "size": size,
            "files": [
                {
                    "id": f.id,
                    "message_id": f.message_id,
                    "folder_id": f.folder_id,
                    "name": f.name,
                    "size": f.size,
                    "mime_type": f.mime_type,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in files
            ],
        }
        for (name, size), files in groups.items()
    ]