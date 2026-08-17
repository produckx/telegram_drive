from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Request, Query
from config.database import get_session, close_session


def resolve_db(request: Request) -> Session:
    """Create and attach DB session to request state."""
    db = get_session()
    request.state.db = db
    return db


def get_db(request: Request) -> Session:
    """Get DB session from request state."""
    if not hasattr(request.state, "db") or request.state.db is None:
        request.state.db = get_session()
    return request.state.db


def close_db(request: Request):
    """Close DB session from request state."""
    if hasattr(request.state, "db") and request.state.db is not None:
        close_session(request.state.db)
        request.state.db = None


def pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> tuple[int, int]:
    """Extract pagination parameters."""
    return page, limit