from pydantic import BaseModel
from typing import List, Optional


class FolderStatResponse(BaseModel):
    id: Optional[int]
    name: str
    file_count: int
    size_bytes: int


class MimeStatResponse(BaseModel):
    mime_type: str
    file_count: int
    size_bytes: int


class StorageStatsResponse(BaseModel):
    total_storage_used_bytes: int
    total_file_count: int
    folders: List[FolderStatResponse]
    mime_types: List[MimeStatResponse]


class DuplicateFileResponse(BaseModel):
    id: int
    message_id: int
    folder_id: Optional[int]
    name: str
    size: int
    mime_type: Optional[str]
    created_at: Optional[str]


class DuplicateGroupResponse(BaseModel):
    name: str
    size: int
    files: List[DuplicateFileResponse]