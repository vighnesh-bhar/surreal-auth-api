"""routers/products.py — Product catalog, lifecycle, SEO, and shipping."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.common import paginated, strip_none
from app.models.product import (
    DuplicateProductRequest,
    ProductCreate,
    ProductSEOUpdate,
    ProductShippingUpdate,
    ProductUpdate,
    RejectProductRequest,
    ShippingRateRequest,
)

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def create_product(data: ProductCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if await db.query("SELECT id FROM product WHERE sku = $sku LIMIT 1", {"sku": data.sku}):
        raise HTTPException(409, ErrorMessages.SKU_ALREADY_EXISTS.value)
    record = await db.create("product", {
        **data.model_dump(),
        "lifecycle_status": "draft",
        "locked": False,
        "created_by": _user["id"],
        "created_at": _NOW(),
        "updated_at": _NOW(),
    })
    await _log(db, record["id"], _user["id"], "created", {})
    return record


@router.get("/")
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    category_id: str = None,
    brand_id: str = None,
    status: str = None,
    sort_by: str = "created_at",
    order: str = "DESC",
    db: DB = Depends(get_db),
):
    conditions = ["status != 'archived'"]
    if category_id:
        conditions.append(f"category_id = '{category_id}'")
    if brand_id:
        conditions.append(f"brand_id = '{brand_id}'")
    if status:
        conditions.append(f"status = '{status}'")
    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * limit
    items = await db.query(f"SELECT * FROM product {where} ORDER BY {sort_by} {order.upper()} LIMIT {limit} START {offset}")
    total = await db.count("product", " AND ".join(conditions))
    return paginated(items, total, page, limit)


@router.get("/{product_id}")
async def get_product(product_id: str, db: DB = Depends(get_db)):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return p


@router.patch("/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    if p.get("locked"):
        raise HTTPException(423, ErrorMessages.PRODUCT_LOCKED.value)
    payload = {**strip_none(data.model_dump()), "updated_at": _NOW()}
    updated = await db.update("product", product_id, payload)
    await _log(db, product_id, _user["id"], "updated", payload)
    return updated


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    await db.update("product", product_id, {"status": "archived", "updated_at": _NOW()})
    await _log(db, product_id, _user["id"], "archived", {})


@router.post("/{product_id}/restore")
async def restore_product(product_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"status": "draft", "updated_at": _NOW()})
    await _log(db, product_id, _user["id"], "restored", {})
    return updated


@router.post("/{product_id}/publish")
async def publish_product(product_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"status": "active", "lifecycle_status": "active", "updated_at": _NOW()})
    await _log(db, product_id, _user["id"], "published", {})
    return updated


@router.post("/{product_id}/unpublish")
async def unpublish_product(product_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"status": "draft", "lifecycle_status": "draft", "updated_at": _NOW()})
    await _log(db, product_id, _user["id"], "unpublished", {})
    return updated


@router.post("/{product_id}/duplicate", status_code=201)
async def duplicate_product(product_id: str, data: DuplicateProductRequest, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    original = await db.select_one("product", product_id)
    if not original:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    suffix = uuid.uuid4().hex[:6]
    new_product = await db.create("product", {
        **{k: v for k, v in original.items() if k != "id"},
        "name": data.new_name,
        "sku": original.get("sku", "") + f"-copy-{suffix}",
        "status": "draft", "lifecycle_status": "draft", "locked": False,
        "created_by": _user["id"], "created_at": _NOW(), "updated_at": _NOW(),
    })
    new_pid = new_product["id"]

    for variant in await db.query("SELECT * FROM variant WHERE product_id = $pid", {"pid": product_id}):
        await db.create("variant", {**{k: v for k, v in variant.items() if k != "id"},
            "product_id": new_pid, "sku": variant.get("sku", "") + f"-copy-{suffix}",
            "created_at": _NOW(), "updated_at": _NOW()})

    for img in await db.query("SELECT * FROM product_image WHERE product_id = $pid", {"pid": product_id}):
        await db.create("product_image", {**{k: v for k, v in img.items() if k != "id"},
            "product_id": new_pid, "created_at": _NOW()})

    for attr in await db.query("SELECT * FROM product_attribute WHERE product_id = $pid", {"pid": product_id}):
        await db.create("product_attribute", {**{k: v for k, v in attr.items() if k != "id"},
            "product_id": new_pid, "created_at": _NOW()})

    await _log(db, new_pid, _user["id"], "duplicated_from", {"source_product_id": product_id})
    return new_product


# Lifecycle

@router.post("/{product_id}/submit-for-review")
async def submit_for_review(product_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"lifecycle_status": "pending_review", "updated_at": _NOW()})
    await _log(db, product_id, _user["id"], "submitted_for_review", {})
    return updated


@router.post("/{product_id}/approve")
async def approve_product(product_id: str, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"lifecycle_status": "approved", "updated_at": _NOW()})
    await _log(db, product_id, _admin["id"], "approved", {})
    return updated


@router.post("/{product_id}/reject")
async def reject_product(product_id: str, data: RejectProductRequest, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update("product", product_id, {"lifecycle_status": "rejected", "reject_reason": data.reason, "updated_at": _NOW()})
    await _log(db, product_id, _admin["id"], "rejected", {"reason": data.reason})
    return updated


@router.get("/{product_id}/changelog")
async def get_changelog(product_id: str, db: DB = Depends(get_db)):
    return await db.query("SELECT * FROM product_changelog WHERE product_id = $pid ORDER BY created_at DESC", {"pid": product_id})


@router.post("/{product_id}/lock")
async def lock_product(product_id: str, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    updated = await db.update("product", product_id, {"locked": True, "updated_at": _NOW()})
    if not updated:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return updated


@router.post("/{product_id}/unlock")
async def unlock_product(product_id: str, db: DB = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    updated = await db.update("product", product_id, {"locked": False, "updated_at": _NOW()})
    if not updated:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return updated


# SEO

@router.patch("/{product_id}/seo")
async def update_seo(product_id: str, data: ProductSEOUpdate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return await db.update("product", product_id, {"seo": strip_none(data.model_dump()), "updated_at": _NOW()})


@router.get("/{product_id}/seo")
async def get_seo(product_id: str, db: DB = Depends(get_db)):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return p.get("seo", {})


# Shipping

@router.patch("/{product_id}/shipping")
async def update_shipping(product_id: str, data: ProductShippingUpdate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    if not await db.select_one("product", product_id):
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return await db.update("product", product_id, {"shipping": strip_none(data.model_dump()), "updated_at": _NOW()})


@router.post("/{product_id}/shipping-rates")
async def get_shipping_rates(product_id: str, data: ShippingRateRequest, db: DB = Depends(get_db)):
    """Returns flat-rate estimates. Swap with a real carrier API (UPS/Shippo) when ready."""
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    weight_kg = (p.get("shipping", {}).get("weight") or 0.5) * data.quantity
    return {
        "product_id": product_id,
        "destination": data.destination,
        "rates": [
            {"carrier": "Standard", "label": "Standard (5-7 days)", "price": round(4.99 + weight_kg * 0.5, 2)},
            {"carrier": "Express",  "label": "Express (2-3 days)",  "price": round(9.99 + weight_kg * 0.8, 2)},
            {"carrier": "Overnight","label": "Overnight",           "price": round(19.99 + weight_kg * 1.2, 2)},
        ],
    }


async def _log(db: DB, product_id: str, user_id: str, action: str, diff: dict):
    await db.create("product_changelog", {
        "product_id": product_id, "user_id": user_id,
        "action": action, "diff": diff, "created_at": _NOW(),
    })
