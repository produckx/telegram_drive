from typing import Optional
from fastapi import HTTPException


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ValidationError(AppException):
    """Validation error."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=422, code="VALIDATION_ERROR")


class UnauthorizedError(AppException):
    """Unauthorized access."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401, code="UNAUTHORIZED")


class ForbiddenError(AppException):
    """Forbidden access."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403, code="FORBIDDEN")


class ConflictError(AppException):
    """Resource conflict."""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, status_code=409, code="CONFLICT")


def to_http_exception(exc: AppException) -> HTTPException:
    """Convert AppException to FastAPI HTTPException."""
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})