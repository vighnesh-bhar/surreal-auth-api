"""models/cart.py — cart, cart items, and coupon schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CartCreate(BaseModel):
    user_id: Optional[str] = None   # None = guest cart


class CartItemAdd(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=0)   # 0 = remove


class CouponApply(BaseModel):
    code: str


class CartMerge(BaseModel):
    guest_cart_id: str
    user_cart_id: str


class CartItem(BaseModel):
    id: str
    product_id: str
    variant_id: Optional[str]
    quantity: int
    unit_price: float
    subtotal: float


class CartResponse(BaseModel):
    id: str
    user_id: Optional[str]
    items: list[CartItem]
    coupon_code: Optional[str]
    status: str


class CartSummary(BaseModel):
    subtotal: float
    discount: float
    coupon_code: Optional[str]
    tax: float
    shipping_estimate: float
    grand_total: float
