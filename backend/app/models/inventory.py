"""models/inventory.py — stock adjustment, reservation, history schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

StockReason = Literal["restock", "return", "damage", "manual", "sale", "reserve", "release"]


class StockAdjust(BaseModel):
    variant_id: Optional[str] = None
    quantity: int = Field(..., description="Positive to add, negative to subtract")
    reason: StockReason = "manual"
    note: str = ""


class StockSet(BaseModel):
    variant_id: Optional[str] = None
    quantity: int = Field(..., ge=0)


class BulkStockUpdate(BaseModel):
    updates: list[dict]   # [{variant_id, quantity, reason}]


class StockReserve(BaseModel):
    variant_id: Optional[str] = None
    quantity: int = Field(..., ge=1)
    order_ref: str


class StockRelease(BaseModel):
    reservation_id: str


class StockResponse(BaseModel):
    product_id: str
    variant_id: Optional[str]
    quantity: int
    reserved: int
    available: int
