"""Shared Pydantic schemas used across multiple routers."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str
    code: str | None = None


class SuccessResponse(BaseModel):
    """Generic success acknowledgement."""

    message: str
    data: dict[str, Any] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated list responses."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int
