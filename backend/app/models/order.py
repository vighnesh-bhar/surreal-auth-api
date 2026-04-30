"""models/order.py — order creation, status, and refund schemas."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

OrderStatus = Literal["pending", "processing", "shipped", "delivered", "cancelled", "refunded"]


class OrderCreate(BaseModel):
    cart_id: str
    shipping_address: dict[str, Any]
    billing_address: dict[str, Any]
    payment_method_id: str
    coupon_code: Optional[str] = None


class OrderCancel(BaseModel):
    reason: str = ""


class RefundItem(BaseModel):
    order_item_id: str
    quantity: int = Field(..., ge=1)


class OrderRefund(BaseModel):
    items: list[RefundItem]
    reason: str = ""
    refund_method: Literal["original", "store_credit"] = "original"


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    variant_id: Optional[str]
    name: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderResponse(BaseModel):
    id: str
    user_id: str
    items: list[OrderItemResponse]
    shipping_address: dict[str, Any]
    billing_address: dict[str, Any]
    status: str
    subtotal: float
    discount: float
    tax: float
    shipping_cost: float
    grand_total: float
    tracking_number: Optional[str]
    carrier: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
