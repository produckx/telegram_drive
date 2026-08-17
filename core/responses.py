from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Simple message response."""

    success: bool = True
    message: str


class DataResponse(BaseModel, Generic[T]):
    """Standard data response wrapper."""

    success: bool = True
    data: T


class ListResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    success: bool = True
    data: list[T]
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: dict = Field(default_factory=dict)


def ok(data: Any = None, message: str = "Success") -> dict:
    """Success response builder."""
    if data is None:
        return {"success": True, "message": message}
    return {"success": True, "data": data}


def error(message: str, code: str = "ERROR", status_code: int = 400) -> dict:
    """Error response builder."""
    return {"success": False, "error": {"code": code, "message": message}}


def paginated(items: list, page: int, limit: int, total: int) -> dict:
    """Paginated list response builder."""
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    return {
        "success": True,
        "data": items,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }