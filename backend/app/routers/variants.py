"""routers/variants.py — §3 Product Variants."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.variant import BulkVariantCreate, VariantCreate, VariantUpdate
from app.models.common import strip_none

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/{product_id}/variants", status_code=201)
async def create_variant(
    product_id: str,
    data: VariantCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    dup = await db.query("SELECT id FROM variant WHERE sku = $sku LIMIT 1", {"sku": data.sku})
    if dup:
        raise HTTPException(409, ErrorMessages.VARIANT_SKU_EXISTS.value)

    record = await db.create(
        "variant",
        {"product_id": product_id, **data.model_dump(), "created_at": _NOW(), "updated_at": _NOW()},
    )
    return record


@router.get("/{product_id}/variants")
async def list_variants(product_id: str, db: DB = Depends(get_db)):
    return await db.query(
        "SELECT * FROM variant WHERE product_id = $pid ORDER BY created_at ASC",
        {"pid": product_id},
    )


@router.patch("/{product_id}/variants/{variant_id}")
async def update_variant(
    product_id: str,
    variant_id: str,
    data: VariantUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    v = await db.select_one("variant", variant_id)
    if not v or v.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.VARIANT_NOT_FOUND.value)

    payload = strip_none(data.model_dump())
    payload["updated_at"] = _NOW()
    return await db.update("variant", variant_id, payload)


@router.delete("/{product_id}/variants/{variant_id}", status_code=204)
async def delete_variant(
    product_id: str,
    variant_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    v = await db.select_one("variant", variant_id)
    if not v or v.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.VARIANT_NOT_FOUND.value)
    await db.delete("variant", variant_id)


@router.post("/{product_id}/variants/bulk", status_code=201)
async def bulk_create_variants(
    product_id: str,
    data: BulkVariantCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    created = []
    errors = []
    for v in data.variants:
        dup = await db.query("SELECT id FROM variant WHERE sku = $sku LIMIT 1", {"sku": v.sku})
        if dup:
            errors.append({"sku": v.sku, "error": "Duplicate SKU"})
            continue
        record = await db.create(
            "variant",
            {"product_id": product_id, **v.model_dump(), "created_at": _NOW(), "updated_at": _NOW()},
        )
        created.append(record)

    return {"created": created, "errors": errors}
