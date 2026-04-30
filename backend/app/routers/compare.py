"""routers/compare.py — §15 Product Comparison."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import CompareAdd, CompareCreate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/compare", status_code=201)
async def start_comparison(data: CompareCreate, db: DB = Depends(get_db)):
    if len(data.product_ids) > 5:
        raise HTTPException(422, ErrorMessages.COMPARISON_MAX_REACHED.value)
    record = await db.create(
        "comparison",
        {"product_ids": data.product_ids, "created_at": _NOW()},
    )
    return record


@router.get("/compare/{compare_id}")
async def get_comparison(compare_id: str, db: DB = Depends(get_db)):
    comp = await db.select_one("comparison", compare_id)
    if not comp:
        raise HTTPException(404, ErrorMessages.COMPARISON_NOT_FOUND.value)

    products = []
    for pid in comp.get("product_ids", []):
        p = await db.select_one("product", pid)
        if not p:
            continue
        # Attach attribute values for side-by-side spec comparison
        attrs = await db.query(
            "SELECT pa.value, a.name AS attribute_name FROM product_attribute AS pa, attribute AS a "
            "WHERE pa.attribute_id = a.id AND pa.product_id = $pid",
            {"pid": pid},
        )
        p["attributes"] = attrs
        products.append(p)
    comp["products"] = products
    return comp


@router.post("/compare/{compare_id}/add")
async def add_to_comparison(compare_id: str, data: CompareAdd, db: DB = Depends(get_db)):
    comp = await db.select_one("comparison", compare_id)
    if not comp:
        raise HTTPException(404, ErrorMessages.COMPARISON_NOT_FOUND.value)
    ids = comp.get("product_ids", [])
    if len(ids) >= 5:
        raise HTTPException(422, ErrorMessages.COMPARISON_FULL.value)
    if data.product_id not in ids:
        ids.append(data.product_id)
        await db.update("comparison", compare_id, {"product_ids": ids})
    return {"product_ids": ids}


@router.delete("/compare/{compare_id}/remove/{product_id}", status_code=204)
async def remove_from_comparison(compare_id: str, product_id: str, db: DB = Depends(get_db)):
    comp = await db.select_one("comparison", compare_id)
    if not comp:
        raise HTTPException(404, ErrorMessages.COMPARISON_NOT_FOUND.value)
    ids = [i for i in comp.get("product_ids", []) if i != product_id]
    await db.update("comparison", compare_id, {"product_ids": ids})
