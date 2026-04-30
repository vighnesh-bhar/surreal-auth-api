"""
models/common.py — shared response shapes, pagination helpers, and utilities.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Pagination(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit

    def to_surql(self) -> str:
        return f"LIMIT {self.limit} START {self.offset}"


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


class MessageResponse(BaseModel):
    message: str


class IDResponse(BaseModel):
    id: str


def paginated(items: list[Any], total: int, page: int, limit: int) -> dict:
    pages = max(1, -(-total // limit))  # ceiling division
    return {"items": items, "total": total, "page": page, "limit": limit, "pages": pages}


def strip_none(d: dict) -> dict:
    """Remove keys with None values — useful for partial PATCH payloads."""
    return {k: v for k, v in d.items() if v is not None}
