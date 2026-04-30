"""models/variant.py — Pydantic schemas for product variants."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


WeightUnit = Literal["kg", "lb", "g", "oz"]


class VariantCreate(BaseModel):
    name: str = ""
    sku: str = Field(..., min_length=1)
    attributes: dict[str, Any] = {}   # {"color": "red", "size": "M"}
    price: float = Field(..., ge=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    stock: int = Field(0, ge=0)
    weight: Optional[float] = None
    weight_unit: WeightUnit = "kg"
    image_id: Optional[str] = None
    is_active: bool = True


class VariantUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    stock: Optional[int] = Field(None, ge=0)
    attributes: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    image_id: Optional[str] = None


class BulkVariantCreate(BaseModel):
    variants: list[VariantCreate]


class VariantResponse(BaseModel):
    id: str
    product_id: str
    name: str
    sku: str
    attributes: dict[str, Any]
    price: float
    compare_at_price: Optional[float]
    stock: int
    weight: Optional[float]
    weight_unit: str
    image_id: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}
