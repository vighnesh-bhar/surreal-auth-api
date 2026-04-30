"""models/review.py — review, Q&A, and rating schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str = ""
    body: str = ""
    verified_purchase: bool = False


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = None
    body: Optional[str] = None


class ReviewModerate(BaseModel):
    status: Literal["approved", "rejected", "flagged"]


class ReviewReport(BaseModel):
    reason: Literal["spam", "offensive", "irrelevant", "fake"]


class ReviewResponse(BaseModel):
    id: str
    product_id: str
    user_id: str
    rating: int
    title: str
    body: str
    verified_purchase: bool
    status: str
    helpful_count: int
    created_at: Optional[str]


class RatingSummary(BaseModel):
    product_id: str
    average: float
    total: int
    distribution: dict[str, int]   # {"5": 10, "4": 5, ...}


class QuestionCreate(BaseModel):
    question: str


class AnswerCreate(BaseModel):
    answer: str
    answered_by: Literal["seller", "user"] = "user"
