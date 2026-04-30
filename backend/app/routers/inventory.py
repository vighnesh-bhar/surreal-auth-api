"""routers/inventory.py — §4 Inventory & Stock."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.inventory import BulkStockUpdate, StockAdjust, StockRelease, StockReserve, StockSet

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.get("/{product_id}/stock")
async def get_stock(product_id: str, db: DB = Depends(get_db)):
    """Get stock level for product + all its variants."""
    variants = await db.query(
        "SELECT id, sku, stock, reserved FROM variant WHERE product_id = $pid",
        {"pid": product_id},
    )
    product = await db.select_one("product", product_id)
    if not product:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    return {
        "product_id": product_id,
        "variants": [
            {
                **v,
                "available": max(0, v.get("stock", 0) - v.get("reserved", 0)),
            }
            for v in variants
        ],
    }


@router.post("/{product_id}/stock/adjust")
async def adjust_stock(
    product_id: str,
    data: StockAdjust,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    target_id = data.variant_id or product_id
    table = "variant" if data.variant_id else "product"

    record = await db.select_one(table, target_id)
    if not record:
        raise HTTPException(404, ErrorMessages.RECORD_NOT_FOUND.value)

    current_stock = record.get("stock", 0)
    new_stock = max(0, current_stock + data.quantity)

    await db.update(table, target_id, {"stock": new_stock, "updated_at": _NOW()})
    await _write_history(db, product_id, data.variant_id, data.quantity, new_stock, data.reason, data.note, _user["id"])
    return {"product_id": product_id, "variant_id": data.variant_id, "new_stock": new_stock}


@router.post("/{product_id}/stock/set")
async def set_stock(
    product_id: str,
    data: StockSet,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    target_id = data.variant_id or product_id
    table = "variant" if data.variant_id else "product"

    record = await db.select_one(table, target_id)
    if not record:
        raise HTTPException(404, ErrorMessages.RECORD_NOT_FOUND.value)

    old = record.get("stock", 0)
    delta = data.quantity - old
    await db.update(table, target_id, {"stock": data.quantity, "updated_at": _NOW()})
    await _write_history(db, product_id, data.variant_id, delta, data.quantity, "manual", "hard set", _user["id"])
    return {"product_id": product_id, "variant_id": data.variant_id, "new_stock": data.quantity}


@router.post("/stock/bulk-update")
async def bulk_stock_update(
    data: BulkStockUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    results = []
    for u in data.updates:
        variant_id = u.get("variant_id")
        quantity = u.get("quantity", 0)
        reason = u.get("reason", "manual")

        v = await db.select_one("variant", variant_id)
        if not v:
            results.append({"variant_id": variant_id, "error": "Not found"})
            continue

        current = v.get("stock", 0)
        new_stock = max(0, current + quantity)
        await db.update("variant", variant_id, {"stock": new_stock, "updated_at": _NOW()})
        await _write_history(db, v.get("product_id", ""), variant_id, quantity, new_stock, reason, "", _user["id"])
        results.append({"variant_id": variant_id, "new_stock": new_stock})
    return results


@router.get("/stock/low")
async def low_stock(
    threshold: int = Query(10, ge=0),
    db: DB = Depends(get_db),
):
    rows = await db.query(
        f"SELECT * FROM variant WHERE stock <= {threshold} AND stock > 0 ORDER BY stock ASC"
    )
    return rows


@router.get("/stock/out-of-stock")
async def out_of_stock(db: DB = Depends(get_db)):
    rows = await db.query("SELECT * FROM variant WHERE stock = 0")
    return rows


@router.post("/{product_id}/stock/reserve")
async def reserve_stock(
    product_id: str,
    data: StockReserve,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    table = "variant" if data.variant_id else "product"
    target_id = data.variant_id or product_id

    record = await db.select_one(table, target_id)
    if not record:
        raise HTTPException(404, ErrorMessages.RESOURCE_NOT_FOUND.value.format(resource=table.capitalize()))

    available = (record.get("stock") or 0) - (record.get("reserved") or 0)
    if available < data.quantity:
        raise HTTPException(
            422,
            ErrorMessages.ONLY_UNITS_AVAILABLE.value.format(available=available, requested=data.quantity),
        )

    # Atomic increment — prevents two concurrent requests from over-reserving
    results = await db.query(
        f"UPDATE {table}:{target_id} SET reserved = (reserved ?? 0) + $qty "
        f"WHERE ((stock ?? 0) - (reserved ?? 0)) >= $qty RETURN AFTER",
        {"qty": data.quantity},
    )
    if not results:
        raise HTTPException(409, ErrorMessages.RESERVATION_CONFLICT.value)

    reservation = await db.create(
        "stock_reservation",
        {
            "product_id": product_id,
            "variant_id": data.variant_id,
            "quantity": data.quantity,
            "order_ref": data.order_ref,
            "status": "active",
            "reserved_by": _user["id"],
            "created_at": _NOW(),
        },
    )
    return reservation


@router.post("/{product_id}/stock/release")
async def release_stock(
    product_id: str,
    data: StockRelease,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    reservation = await db.select_one("stock_reservation", data.reservation_id)
    if not reservation:
        raise HTTPException(404, ErrorMessages.RESERVATION_NOT_FOUND.value)
    if reservation.get("status") != "active":
        raise HTTPException(409, ErrorMessages.RESERVATION_ALREADY_RELEASED.value)

    variant_id = reservation.get("variant_id")
    qty = reservation.get("quantity", 0)
    table = "variant" if variant_id else "product"
    target_id = variant_id or product_id

    record = await db.select_one(table, target_id)
    if record:
        reserved = max(0, record.get("reserved", 0) - qty)
        await db.update(table, target_id, {"reserved": reserved, "updated_at": _NOW()})

    await db.update("stock_reservation", data.reservation_id, {"status": "released", "released_at": _NOW()})
    return {"message": SuccessMessages.RESERVATION_RELEASED.value, "reservation_id": data.reservation_id}


@router.get("/{product_id}/stock/history")
async def stock_history(
    product_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    reason: Optional[str] = None,
    db: DB = Depends(get_db),
):
    conditions = [f"product_id = '{product_id}'"]
    if from_date:
        conditions.append(f"created_at >= '{from_date}'")
    if to_date:
        conditions.append(f"created_at <= '{to_date}'")
    if reason:
        conditions.append(f"reason = '{reason}'")

    where = "WHERE " + " AND ".join(conditions)
    return await db.query(
        f"SELECT * FROM stock_history {where} ORDER BY created_at DESC"
    )



async def _write_history(
    db: DB, product_id: str, variant_id: Optional[str], delta: int,
    new_stock: int, reason: str, note: str, user_id: str,
):
    await db.create(
        "stock_history",
        {
            "product_id": product_id,
            "variant_id": variant_id,
            "delta": delta,
            "new_stock": new_stock,
            "reason": reason,
            "note": note,
            "user_id": user_id,
            "created_at": _NOW(),
        },
    )
