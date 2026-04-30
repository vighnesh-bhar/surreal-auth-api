"""routers/bulk.py — §20 Import/Export & Bulk Operations."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


class BulkProductIDs(BaseModel):
    product_ids: list[str]


class BulkPriceUpdateItem(BaseModel):
    product_id: str
    price: float


class BulkPriceUpdateBody(BaseModel):
    updates: list[BulkPriceUpdateItem]


class BulkCategoryUpdate(BaseModel):
    product_ids: list[str]
    category_id: str


@router.post("/import")
async def import_products(
    file: UploadFile = File(...),
    mode: str = Form("upsert"),
    dry_run: bool = Form(False),
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    MAX_ROWS = 500
    content = await file.read()
    if not content:
        raise HTTPException(422, ErrorMessages.EMPTY_FILE.value)

    filename = file.filename or ""
    content_type = file.content_type or ""
    rows: list[dict] = []

    if "json" in content_type or filename.endswith(".json"):
        try:
            rows = json.loads(content.decode("utf-8"))
            if not isinstance(rows, list):
                raise HTTPException(422, ErrorMessages.JSON_ARRAY_REQUIRED.value)
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(422, ErrorMessages.INVALID_JSON.value.format(error=e))
    else:
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
            rows = list(reader)
        except Exception as e:
            raise HTTPException(422, ErrorMessages.INVALID_CSV.value.format(error=e))

    if len(rows) > MAX_ROWS:
        raise HTTPException(
            422,
            ErrorMessages.TOO_MANY_ROWS.value.format(rows=len(rows), max_rows=MAX_ROWS),
        )

    created = updated = skipped = 0
    errors: list[dict] = []
    preview: list[dict] = []

    for idx, row in enumerate(rows):
        row_num = idx + 1
        name = (row.get("name") or "").strip()
        sku  = (row.get("sku") or "").strip()
        if not name or not sku:
            errors.append({"row": row_num, "error": "Missing required fields: name, sku"})
            continue

        try:
            price = float(row.get("price") or 0)
        except ValueError:
            errors.append({"row": row_num, "sku": sku, "error": "Invalid price value"})
            continue

        tags_raw = row.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if isinstance(tags_raw, str) else (tags_raw or [])

        product_data = {
            "name": name,
            "sku": sku,
            "description": row.get("description", ""),
            "price": price,
            "status": row.get("status", "draft"),
            "category_id": row.get("category_id") or None,
            "brand_id": row.get("brand_id") or None,
            "tags": tags,
            "metadata": {},
            "updated_at": _NOW(),
        }

        existing = await db.query("SELECT id FROM product WHERE sku = $sku LIMIT 1", {"sku": sku})

        if dry_run:
            action = "skip" if (existing and mode == "create_only") else ("update" if existing else "create")
            preview.append({"row": row_num, "sku": sku, "action": action, "name": name})
            continue

        if existing:
            if mode == "create_only":
                skipped += 1
                continue
            eid = str(existing[0]["id"]).split(":")[-1]
            await db.update("product", eid, product_data)
            updated += 1
        else:
            product_data["created_at"] = _NOW()
            product_data["created_by"] = _admin["id"]
            await db.create("product", product_data)
            created += 1

    result: dict = {"created": created, "updated": updated, "skipped": skipped,
                    "errors": errors, "total_rows": len(rows)}
    if dry_run:
        result["dry_run"] = True
        result["preview"] = preview
    return result


@router.get("/export")
async def export_products(
    format: Literal["csv", "json"] = Query("json"),
    status: str | None = None,
    category_id: str | None = None,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    conditions = []
    if status:
        conditions.append(f"status = '{status}'")
    if category_id:
        conditions.append(f"category_id = '{category_id}'")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    products = await db.query(f"SELECT * FROM product {where} ORDER BY created_at DESC")

    if format == "json":
        content = json.dumps(products, indent=2, default=str)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=products.json"},
        )

    # CSV export
    if not products:
        raise HTTPException(404, ErrorMessages.NO_PRODUCTS_TO_EXPORT.value)

    output = io.StringIO()
    fieldnames = list(products[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(products)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.read().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


@router.post("/bulk/delete", status_code=204)
async def bulk_delete(
    data: BulkProductIDs,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    for pid in data.product_ids:
        await db.update("product", pid, {"status": "archived", "updated_at": _NOW()})


@router.post("/bulk/publish")
async def bulk_publish(
    data: BulkProductIDs,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    for pid in data.product_ids:
        await db.update("product", pid, {"status": "active", "updated_at": _NOW()})
    return {"message": f"{len(data.product_ids)} products published"}


@router.post("/bulk/update-price")
async def bulk_update_price(
    data: BulkPriceUpdateBody,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    results = []
    for u in data.updates:
        updated = await db.update("product", u.product_id, {"price": u.price, "updated_at": _NOW()})
        results.append({"product_id": u.product_id, "ok": bool(updated)})
    return results


@router.post("/bulk/update-category")
async def bulk_update_category(
    data: BulkCategoryUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    for pid in data.product_ids:
        await db.update("product", pid, {"category_id": data.category_id, "updated_at": _NOW()})
    return {"message": f"{len(data.product_ids)} products moved to category {data.category_id}"}
