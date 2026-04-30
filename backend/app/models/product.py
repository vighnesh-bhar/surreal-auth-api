"""models/product.py — Pydantic schemas for products."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ProductStatus = Literal["draft", "active", "archived"]
LifecycleStatus = Literal["draft", "pending_review", "approved", "rejected", "active", "archived"]


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    tags: list[str] = []
    status: ProductStatus = "draft"
    sku: str = Field(..., min_length=1)
    metadata: dict[str, Any] = {}


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[ProductStatus] = None
    metadata: Optional[dict[str, Any]] = None


class ProductSEOUpdate(BaseModel):
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    slug: Optional[str] = None
    canonical_url: Optional[str] = None
    og_image_id: Optional[str] = None


class ProductShippingUpdate(BaseModel):
    weight: Optional[float] = None
    weight_unit: Optional[Literal["kg", "lb"]] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    dimension_unit: Optional[Literal["cm", "in"]] = None
    requires_shipping: Optional[bool] = None
    is_fragile: Optional[bool] = None
    shipping_class: Optional[str] = None


class ShippingRateRequest(BaseModel):
    destination: dict[str, str]   # {"country": ..., "state": ..., "zip": ...}
    quantity: int = 1


class DuplicateProductRequest(BaseModel):
    new_name: str


class RejectProductRequest(BaseModel):
    reason: str


class ProductResponse(BaseModel):
    id: str
    name: str
    description: str
    category_id: Optional[str]
    brand_id: Optional[str]
    tags: list[str]
    status: str
    sku: str
    metadata: dict[str, Any]
    created_at: Optional[str]
    updated_at: Optional[str]
    seo: Optional[dict] = None
    shipping: Optional[dict] = None
    locked: bool = False
    lifecycle_status: Optional[str] = None

    model_config = {"from_attributes": True}
