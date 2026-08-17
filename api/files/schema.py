from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FileBase(BaseModel):
    name: str
    size: int
    mime_type: Optional[str] = None
    folder_id: Optional[int] = None


class FileCreate(FileBase):
    message_id: int


class FileUpdate(BaseModel):
    name: Optional[str] = None
    folder_id: Optional[int] = None
    source_folder_id: Optional[int] = None


class FileResponse(FileBase):
    id: int
    message_id: int
    folder_id: Optional[int]
    created_at: datetime
    encryption_state: Optional[str] = "plain"
    is_favorite: bool = False
    is_pinned: bool = False

    class Config:
        from_attributes = True


class FilesListResponse(BaseModel):
    data: List[FileResponse]
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class FileUploadResponse(FileResponse):
    pass


class BulkActionRequest(BaseModel):
    action: str = Field(..., pattern="^(archive|delete|move)$")
    file_ids: List[int]
    folder_id: Optional[int] = None
    payload: Optional[dict] = None


class BulkActionResponse(BaseModel):
    success: bool
    count: int


class CopyFileRequest(BaseModel):
    folder_id: int
    source_folder_id: Optional[int] = None