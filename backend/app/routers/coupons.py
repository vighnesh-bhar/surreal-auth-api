"""routers/coupons.py — §25 Coupons & Promotions."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import CouponCreate, CouponValidate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def create_coupon(
    data: CouponCreate, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)
):
    dup = await db.query("SELECT id FROM coupon WHERE code = $code LIMIT 1", {"code": data.code})
    if dup:
        raise HTTPException(409, ErrorMessages.COUPON_ALREADY_EXISTS.value)
    record = await db.create(
        "coupon",
        {**data.model_dump(), "is_active": True, "usage_count": 0, "created_at": _NOW()},
    )
    return record


@router.get("/")
async def list_coupons(db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    return await db.query("SELECT * FROM coupon ORDER BY created_at DESC")


@router.post("/validate")
async def validate_coupon(data: CouponValidate, db: DB = Depends(get_db)):
    coupons = await db.query(
        "SELECT * FROM coupon WHERE code = $code AND is_active = true LIMIT 1",
        {"code": data.code},
    )
    if not coupons:
        raise HTTPException(422, ErrorMessages.COUPON_INVALID_OR_EXPIRED.value)

    coupon = coupons[0]
    now = _NOW()

    if coupon.get("starts_at") and coupon["starts_at"] > now:
        raise HTTPException(422, ErrorMessages.COUPON_NOT_YET_ACTIVE.value)
    if coupon.get("ends_at") and coupon["ends_at"] < now:
        raise HTTPException(422, ErrorMessages.COUPON_EXPIRED.value)

    usage_limit = coupon.get("usage_limit")
    if usage_limit and coupon.get("usage_count", 0) >= usage_limit:
        raise HTTPException(422, ErrorMessages.COUPON_USAGE_LIMIT.value)

    # Get cart value to check minimum order
    cart = await db.select_one("cart", data.cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)

    items = await db.query(
        "SELECT math::sum(subtotal) AS total FROM cart_item WHERE cart_id = $cid GROUP ALL",
        {"cid": data.cart_id},
    )
    cart_total = items[0]["total"] if items else 0

    min_order = coupon.get("min_order_value", 0)
    if cart_total < min_order:
        raise HTTPException(422, ErrorMessages.CART_MIN_TOTAL.value.format(min_order=min_order))

    # Calculate discount
    if coupon["type"] == "percentage":
        discount = round(cart_total * coupon["value"] / 100, 2)
    elif coupon["type"] == "fixed":
        discount = min(coupon["value"], cart_total)
    else:  # free_shipping
        discount = 0  # handled at checkout

    return {
        "valid": True,
        "coupon": coupon,
        "cart_total": cart_total,
        "discount": discount,
        "type": coupon["type"],
    }


@router.delete("/{coupon_id}", status_code=204)
async def delete_coupon(
    coupon_id: str, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)
):
    ok = await db.update("coupon", coupon_id, {"is_active": False})
    if not ok:
        raise HTTPException(404, ErrorMessages.NOT_FOUND.value)
