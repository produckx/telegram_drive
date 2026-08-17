from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FolderBase(BaseModel):
    name: str
    parent_id: Optional[int] = None
    username: Optional[str] = None
    is_public: bool = False


class FolderCreate(FolderBase):
    pass


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    is_public: Optional[bool] = None


class FolderResponse(FolderBase):
    id: int
    display_order: int
    group_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


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


class DuplicateGroupResponse(BaseModel):
    name: str
    size: int
    files: List[dict]