"""routers/orders.py — §13 Orders."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.order import OrderCancel, OrderCreate, OrderRefund, OrderStatusUpdate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def place_order(
    data: OrderCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    # 1. Validate cart
    cart = await db.select_one("cart", data.cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)
    if cart.get("status") == "completed":
        raise HTTPException(409, ErrorMessages.CART_ALREADY_USED.value)

    # 2. Fetch cart items
    items = await db.query(
        "SELECT * FROM cart_item WHERE cart_id = $cid", {"cid": data.cart_id}
    )
    if not items:
        raise HTTPException(422, ErrorMessages.CART_EMPTY.value)

    # 3. Check stock for each item
    for item in items:
        table = "variant" if item.get("variant_id") else "product"
        target = item.get("variant_id") or item["product_id"]
        record = await db.select_one(table, target)
        if not record:
            raise HTTPException(
                422,
                ErrorMessages.PRODUCT_NO_LONGER_EXISTS.value.format(product_id=item["product_id"]),
            )
        available = (record.get("stock") or 0) - (record.get("reserved") or 0)
        if available < item["quantity"]:
            raise HTTPException(
                422,
                f"Insufficient stock for '{record.get('name', item['product_id'])}': "
                f"{available} available, {item['quantity']} requested",
            )

    # 4. Calculate totals
    subtotal = round(sum(item.get("subtotal", 0) for item in items), 2)
    discount = 0.0
    coupon_code = data.coupon_code or cart.get("coupon_code")
    coupon_rows = []
    if coupon_code:
        coupon_rows = await db.query(
            "SELECT * FROM coupon WHERE code = $c AND is_active = true LIMIT 1",
            {"c": coupon_code},
        )
        if coupon_rows:
            c = coupon_rows[0]
            if c["type"] == "percentage":
                discount = round(subtotal * c["value"] / 100, 2)
            elif c["type"] == "fixed":
                discount = round(min(c["value"], subtotal), 2)
            # free_shipping handled below

    TAX_RATE = 0.08
    FREE_SHIPPING_THRESHOLD = 50.0
    FLAT_SHIPPING = 5.99
    free_shipping = coupon_rows and coupon_rows[0].get("type") == "free_shipping"
    taxable = subtotal - discount
    tax = round(taxable * TAX_RATE, 2)
    shipping_cost = 0.0 if (free_shipping or subtotal >= FREE_SHIPPING_THRESHOLD) else FLAT_SHIPPING
    grand_total = round(taxable + tax + shipping_cost, 2)

    # 5. Create the order record
    order = await db.create(
        "order",
        {
            "user_id": _user["id"],
            "cart_id": data.cart_id,
            "shipping_address": data.shipping_address,
            "billing_address": data.billing_address,
            "payment_method_id": data.payment_method_id,
            "coupon_code": coupon_code,
            "status": "pending",
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "shipping_cost": shipping_cost,
            "grand_total": grand_total,
            "tracking_number": None,
            "carrier": None,
            "created_at": _NOW(),
            "updated_at": _NOW(),
        },
    )

    # 6. Create order_item records (snapshot name + price at purchase time)
    for item in items:
        product = await db.select_one("product", item["product_id"])
        await db.create(
            "order_item",
            {
                "order_id": order["id"],
                "product_id": item["product_id"],
                "variant_id": item.get("variant_id"),
                "name": product.get("name", "") if product else "",
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "subtotal": item["subtotal"],
                "refunded_qty": 0,
                "created_at": _NOW(),
            },
        )

    # 7. Deduct stock
    for item in items:
        table = "variant" if item.get("variant_id") else "product"
        target = item.get("variant_id") or item["product_id"]
        record = await db.select_one(table, target)
        if record:
            new_stock = max(0, record.get("stock", 0) - item["quantity"])
            await db.update(table, target, {"stock": new_stock, "updated_at": _NOW()})

    # 8. Mark cart completed
    await db.update("cart", data.cart_id, {"status": "completed", "updated_at": _NOW()})

    # 9. Increment coupon usage
    if coupon_rows:
        cid = str(coupon_rows[0]["id"]).split(":")[-1]
        await db.update("coupon", cid, {"usage_count": coupon_rows[0].get("usage_count", 0) + 1})

    order["items"] = await db.query(
        "SELECT * FROM order_item WHERE order_id = $oid", {"oid": order["id"]}
    )
    return order


@router.get("/")
async def list_orders(
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await db.query(
        "SELECT * FROM order WHERE user_id = $uid ORDER BY created_at DESC",
        {"uid": _user["id"]},
    )


@router.get("/{order_id}")
async def get_order(
    order_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    if order["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    items = await db.query(
        "SELECT * FROM order_item WHERE order_id = $oid", {"oid": order_id}
    )
    order["items"] = items
    return order


@router.patch("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    data: OrderCancel,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    if order["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    if order["status"] not in ("pending", "processing"):
        raise HTTPException(
            409,
            ErrorMessages.ORDER_CANNOT_CANCEL_STATUS.value.format(status=order["status"]),
        )

    updated = await db.update(
        "order", order_id,
        {"status": "cancelled", "cancel_reason": data.reason, "updated_at": _NOW()},
    )
    # Release stock reservations for this order
    reservations = await db.query(
        "SELECT * FROM stock_reservation WHERE order_ref = $oid AND status = 'active'",
        {"oid": order_id},
    )
    for res in reservations:
        res_id = str(res["id"]).split(":")[-1]
        vid = res.get("variant_id")
        qty = res.get("quantity", 0)
        table = "variant" if vid else "product"
        target = vid or order.get("product_id", "")
        record = await db.select_one(table, target)
        if record:
            reserved = max(0, record.get("reserved", 0) - qty)
            await db.update(table, target, {"reserved": reserved})
        await db.update("stock_reservation", res_id, {"status": "released"})
    return updated


@router.post("/{order_id}/refund")
async def refund_order(
    order_id: str,
    data: OrderRefund,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    # 1. Load and authorise
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    if order["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    if order["status"] not in ("delivered", "processing", "shipped"):
        raise HTTPException(
            409,
            ErrorMessages.ORDER_CANNOT_REFUND_STATUS.value.format(status=order["status"]),
        )

    # 2. Validate each line item
    validated = []
    for ri in data.items:
        oi = await db.select_one("order_item", ri.order_item_id)
        if not oi or oi.get("order_id") != order_id:
            raise HTTPException(
                404,
                ErrorMessages.ORDER_ITEM_NOT_FOUND_IN_ORDER.value.format(item_id=ri.order_item_id),
            )
        returnable = oi["quantity"] - oi.get("refunded_qty", 0)
        if ri.quantity > returnable:
            raise HTTPException(
                422,
                ErrorMessages.ORDER_ITEM_REFUND_LIMIT.value.format(
                    returnable=returnable, item_id=ri.order_item_id
                ),
            )
        validated.append(
            {"oi": oi, "oi_id": ri.order_item_id, "qty": ri.quantity,
             "amount": round(oi["unit_price"] * ri.quantity, 2)}
        )

    # 3. Create refund record
    total_refund = round(sum(v["amount"] for v in validated), 2)
    refund_record = await db.create(
        "refund",
        {
            "order_id": order_id,
            "user_id": _user["id"],
            "items": [{"order_item_id": v["oi_id"], "quantity": v["qty"], "amount": v["amount"]} for v in validated],
            "total": total_refund,
            "reason": data.reason,
            "refund_method": data.refund_method,
            "status": "pending",
            "created_at": _NOW(),
        },
    )

    # 4. Update order_items + restore stock
    for v in validated:
        oi = v["oi"]
        new_refunded = oi.get("refunded_qty", 0) + v["qty"]
        await db.update("order_item", v["oi_id"], {"refunded_qty": new_refunded})
        table = "variant" if oi.get("variant_id") else "product"
        target = oi.get("variant_id") or oi["product_id"]
        record = await db.select_one(table, target)
        if record:
            await db.update(table, target, {"stock": record.get("stock", 0) + v["qty"], "updated_at": _NOW()})

    # 5. Update order status if fully refunded
    all_items = await db.query("SELECT * FROM order_item WHERE order_id = $oid", {"oid": order_id})
    fully_refunded = all(oi.get("refunded_qty", 0) >= oi["quantity"] for oi in all_items)
    if fully_refunded:
        await db.update("order", order_id, {"status": "refunded", "updated_at": _NOW()})

    return refund_record


@router.get("/{order_id}/tracking")
async def order_tracking(order_id: str, db: DB = Depends(get_db)):
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    return {
        "order_id": order_id,
        "status": order.get("status"),
        "tracking_number": order.get("tracking_number"),
        "carrier": order.get("carrier"),
        "updated_at": order.get("updated_at"),
    }


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    data: OrderStatusUpdate,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    payload = {
        "status": data.status,
        "updated_at": _NOW(),
    }
    if data.tracking_number:
        payload["tracking_number"] = data.tracking_number
    if data.carrier:
        payload["carrier"] = data.carrier
    return await db.update("order", order_id, payload)


@router.post("/{order_id}/invoice")
async def generate_invoice(
    order_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """
    Generates a basic invoice. Integrate ReportLab or WeasyPrint for real PDF generation.
    Returns JSON invoice data for now; swap the return for a FileResponse.
    """
    order = await db.select_one("order", order_id)
    if not order:
        raise HTTPException(404, ErrorMessages.ORDER_NOT_FOUND.value)
    if order["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)

    items = await db.query(
        "SELECT * FROM order_item WHERE order_id = $oid", {"oid": order_id}
    )
    return {
        "invoice_number": f"INV-{order_id[:8].upper()}",
        "order": order,
        "items": items,
        "generated_at": _NOW(),
        "note": "Integrate ReportLab / WeasyPrint to return an actual PDF FileResponse",
    }


@router.post("/{order_id}/download/{asset_id}")
async def generate_download_url(
    order_id: str,
    asset_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Generate a signed, time-limited download URL for a digital asset after purchase."""
    import secrets, time

    order = await db.select_one("order", order_id)
    if not order or order["user_id"] != _user["id"]:
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    if order.get("status") not in ("processing", "delivered"):
        raise HTTPException(403, ErrorMessages.ORDER_NOT_FULFILLED.value)

    asset = await db.select_one("digital_asset", asset_id)
    if not asset:
        raise HTTPException(404, ErrorMessages.ASSET_NOT_FOUND.value)

    # Store a signed token in DB (expires after 24h)
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 86400
    await db.create(
        "download_token",
        {
            "token": token,
            "asset_id": asset_id,
            "order_id": order_id,
            "user_id": _user["id"],
            "expires_at": expires_at,
            "downloads_used": 0,
        },
    )
    return {
        "download_url": f"/api/v1/downloads/{token}",
        "expires_in_hours": 24,
    }
