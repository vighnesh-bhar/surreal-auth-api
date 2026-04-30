"""routers/categories.py — §6 Categories & Collections."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.misc import (
    CategoryCreate, CategoryUpdate, CategoryProductAssign,
    CollectionCreate, CollectionProductAdd,
)
from app.models.common import strip_none

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

# ── Categories ─────────────────────────────────────────────────────────────────

@router.post("/categories", status_code=201)
async def create_category(data: CategoryCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    dup = await db.query("SELECT id FROM category WHERE slug = $slug LIMIT 1", {"slug": data.slug})
    if dup:
        raise HTTPException(409, ErrorMessages.CATEGORY_SLUG_EXISTS.value)
    record = await db.create("category", {**data.model_dump(), "created_at": _NOW()})
    return record

@router.get("/categories")
async def list_categories(db: DB = Depends(get_db)):
    """Returns flat list; frontend can build tree from parent_id."""
    return await db.query("SELECT * FROM category ORDER BY name ASC")

@router.patch("/categories/{category_id}")
async def update_category(
    category_id: str, data: CategoryUpdate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    payload = strip_none(data.model_dump())
    updated = await db.update("category", category_id, payload)
    if not updated:
        raise HTTPException(404, ErrorMessages.CATEGORY_NOT_FOUND.value)
    return updated

@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: str, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    ok = await db.delete("category", category_id)
    if not ok:
        raise HTTPException(404, ErrorMessages.CATEGORY_NOT_FOUND.value)

@router.post("/categories/{category_id}/products", status_code=201)
async def add_product_to_category(
    category_id: str, data: CategoryProductAssign,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    await db.update("product", data.product_id, {"category_id": category_id, "updated_at": _NOW()})
    return {"message": SuccessMessages.PRODUCT_ASSIGNED_TO_CATEGORY.value}

@router.delete("/categories/{category_id}/products/{product_id}", status_code=204)
async def remove_product_from_category(
    category_id: str, product_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p or p.get("category_id") != category_id:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_IN_CATEGORY.value)
    await db.update("product", product_id, {"category_id": None, "updated_at": _NOW()})

# ── Collections ────────────────────────────────────────────────────────────────

@router.post("/collections", status_code=201)
async def create_collection(data: CollectionCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    record = await db.create("collection", {**data.model_dump(), "created_at": _NOW()})
    return record

@router.get("/collections")
async def list_collections(db: DB = Depends(get_db)):
    return await db.query("SELECT * FROM collection ORDER BY name ASC")

@router.post("/collections/{collection_id}/products", status_code=201)
async def add_to_collection(
    collection_id: str, data: CollectionProductAdd,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    col = await db.select_one("collection", collection_id)
    if not col:
        raise HTTPException(404, ErrorMessages.COLLECTION_NOT_FOUND.value)
    ids = col.get("product_ids", [])
    if data.product_id not in ids:
        ids.append(data.product_id)
        await db.update("collection", collection_id, {"product_ids": ids})
    return {"message": SuccessMessages.PRODUCT_ADDED_TO_COLLECTION.value}

@router.delete("/collections/{collection_id}/products/{product_id}", status_code=204)
async def remove_from_collection(
    collection_id: str, product_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    col = await db.select_one("collection", collection_id)
    if not col:
        raise HTTPException(404, ErrorMessages.COLLECTION_NOT_FOUND.value)
    ids = [i for i in col.get("product_ids", []) if i != product_id]
    await db.update("collection", collection_id, {"product_ids": ids})
