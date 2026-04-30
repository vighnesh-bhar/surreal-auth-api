"""routers/cart.py — §9 Cart."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.cart import CartCreate, CartItemAdd, CartItemUpdate, CouponApply, CartMerge

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def create_cart(data: CartCreate, db: DB = Depends(get_db)):
    record = await db.create(
        "cart",
        {
            "user_id": data.user_id,
            "status": "active",
            "coupon_code": None,
            "created_at": _NOW(),
            "updated_at": _NOW(),
        },
    )
    return record


@router.get("/{cart_id}")
async def get_cart(cart_id: str, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)
    items = await db.query(
        "SELECT * FROM cart_item WHERE cart_id = $cid", {"cid": cart_id}
    )
    cart["items"] = items
    return cart


@router.post("/{cart_id}/items", status_code=201)
async def add_cart_item(cart_id: str, data: CartItemAdd, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)

    # Fetch current price
    product = await db.select_one("product", data.product_id)
    if not product:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    unit_price = product.get("price", 0.0)
    if data.variant_id:
        variant = await db.select_one("variant", data.variant_id)
        if variant:
            unit_price = variant.get("price", unit_price)

    # Check if item already in cart → update quantity instead
    existing = await db.query(
        "SELECT * FROM cart_item WHERE cart_id = $cid AND product_id = $pid AND variant_id = $vid LIMIT 1",
        {"cid": cart_id, "pid": data.product_id, "vid": data.variant_id or ""},
    )
    if existing:
        item = existing[0]
        item_id = str(item["id"]).split(":")[-1]
        new_qty = item["quantity"] + data.quantity
        return await db.update("cart_item", item_id, {
            "quantity": new_qty,
            "subtotal": round(unit_price * new_qty, 2),
            "updated_at": _NOW(),
        })

    record = await db.create(
        "cart_item",
        {
            "cart_id": cart_id,
            "product_id": data.product_id,
            "variant_id": data.variant_id,
            "quantity": data.quantity,
            "unit_price": unit_price,
            "subtotal": round(unit_price * data.quantity, 2),
            "created_at": _NOW(),
            "updated_at": _NOW(),
        },
    )
    await db.update("cart", cart_id, {"updated_at": _NOW()})
    return record


@router.patch("/{cart_id}/items/{item_id}")
async def update_cart_item(
    cart_id: str, item_id: str, data: CartItemUpdate, db: DB = Depends(get_db)
):
    item = await db.select_one("cart_item", item_id)
    if not item or item.get("cart_id") != cart_id:
        raise HTTPException(404, ErrorMessages.CART_ITEM_NOT_FOUND.value)

    if data.quantity == 0:
        await db.delete("cart_item", item_id)
        return {"message": SuccessMessages.ITEM_REMOVED.value}

    unit_price = item.get("unit_price", 0.0)
    return await db.update("cart_item", item_id, {
        "quantity": data.quantity,
        "subtotal": round(unit_price * data.quantity, 2),
        "updated_at": _NOW(),
    })


@router.delete("/{cart_id}/items/{item_id}", status_code=204)
async def remove_cart_item(cart_id: str, item_id: str, db: DB = Depends(get_db)):
    item = await db.select_one("cart_item", item_id)
    if not item or item.get("cart_id") != cart_id:
        raise HTTPException(404, ErrorMessages.CART_ITEM_NOT_FOUND.value)
    await db.delete("cart_item", item_id)


@router.delete("/{cart_id}/clear", status_code=204)
async def clear_cart(cart_id: str, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)
    await db.query("DELETE cart_item WHERE cart_id = $cid", {"cid": cart_id})
    await db.update("cart", cart_id, {"coupon_code": None, "updated_at": _NOW()})


@router.post("/{cart_id}/coupon")
async def apply_coupon(cart_id: str, data: CouponApply, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)
    coupon = await db.query(
        "SELECT * FROM coupon WHERE code = $code AND is_active = true LIMIT 1",
        {"code": data.code},
    )
    if not coupon:
        raise HTTPException(422, ErrorMessages.COUPON_INVALID_OR_EXPIRED.value)
    await db.update("cart", cart_id, {"coupon_code": data.code, "updated_at": _NOW()})
    return {"message": SuccessMessages.COUPON_APPLIED.value, "coupon_code": data.code}


@router.delete("/{cart_id}/coupon", status_code=204)
async def remove_coupon(cart_id: str, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)
    await db.update("cart", cart_id, {"coupon_code": None, "updated_at": _NOW()})


@router.post("/merge")
async def merge_carts(data: CartMerge, db: DB = Depends(get_db)):
    guest_cart = await db.select_one("cart", data.guest_cart_id)
    user_cart = await db.select_one("cart", data.user_cart_id)
    if not guest_cart:
        raise HTTPException(404, ErrorMessages.GUEST_CART_NOT_FOUND.value)
    if not user_cart:
        raise HTTPException(404, ErrorMessages.USER_CART_NOT_FOUND.value)

    guest_items = await db.query(
        "SELECT * FROM cart_item WHERE cart_id = $cid", {"cid": data.guest_cart_id}
    )

    for gi in guest_items:
        gi_id = str(gi["id"]).split(":")[-1]
        # Check if same product+variant already in user cart
        existing = await db.query(
            "SELECT * FROM cart_item WHERE cart_id = $cid AND product_id = $pid LIMIT 1",
            {"cid": data.user_cart_id, "pid": gi["product_id"]},
        )
        if existing:
            ei = existing[0]
            ei_id = str(ei["id"]).split(":")[-1]
            new_qty = ei["quantity"] + gi["quantity"]
            await db.update("cart_item", ei_id, {
                "quantity": new_qty,
                "subtotal": round(ei["unit_price"] * new_qty, 2),
                "updated_at": _NOW(),
            })
            await db.delete("cart_item", gi_id)
        else:
            await db.update("cart_item", gi_id, {"cart_id": data.user_cart_id, "updated_at": _NOW()})

    await db.delete("cart", data.guest_cart_id)
    merged_items = await db.query(
        "SELECT * FROM cart_item WHERE cart_id = $cid", {"cid": data.user_cart_id}
    )
    user_cart["items"] = merged_items
    return user_cart


@router.get("/{cart_id}/summary")
async def cart_summary(cart_id: str, db: DB = Depends(get_db)):
    cart = await db.select_one("cart", cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)

    rows = await db.query(
        "SELECT math::sum(subtotal) AS total FROM cart_item WHERE cart_id = $cid GROUP ALL",
        {"cid": cart_id},
    )
    subtotal = round(rows[0]["total"] if rows and rows[0].get("total") else 0.0, 2)

    discount = 0.0
    free_shipping = False
    coupon_code = cart.get("coupon_code")
    if coupon_code:
        c_rows = await db.query(
            "SELECT * FROM coupon WHERE code = $c AND is_active = true LIMIT 1", {"c": coupon_code}
        )
        if c_rows:
            c = c_rows[0]
            if c["type"] == "percentage":
                discount = round(subtotal * c["value"] / 100, 2)
            elif c["type"] == "fixed":
                discount = round(min(c["value"], subtotal), 2)
            elif c["type"] == "free_shipping":
                free_shipping = True

    taxable = subtotal - discount
    tax = round(taxable * 0.08, 2)
    shipping = 0.0 if (free_shipping or subtotal >= 50.0) else 5.99
    grand_total = round(taxable + tax + shipping, 2)

    return {
        "subtotal": subtotal,
        "discount": discount,
        "coupon_code": coupon_code,
        "tax": tax,
        "shipping_estimate": shipping,
        "grand_total": grand_total,
    }
