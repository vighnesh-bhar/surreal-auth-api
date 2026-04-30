"""routers/attributes.py — §7 Product Attributes & Specifications."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import AttributeCreate, ProductAttributeAssign, ProductAttributeUpdate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/attributes", status_code=201)
async def create_attribute(data: AttributeCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    record = await db.create("attribute", {**data.model_dump(), "created_at": _NOW()})
    return record


@router.get("/attributes")
async def list_attributes(db: DB = Depends(get_db)):
    return await db.query("SELECT * FROM attribute ORDER BY name ASC")


@router.post("/products/{product_id}/attributes", status_code=201)
async def assign_attributes(
    product_id: str, data: ProductAttributeAssign,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    created = []
    for attr in data.attributes:
        record = await db.create(
            "product_attribute",
            {
                "product_id": product_id,
                "attribute_id": attr["attribute_id"],
                "value": attr["value"],
                "created_at": _NOW(),
            },
        )
        created.append(record)
    return created


@router.patch("/products/{product_id}/attributes/{attribute_id}")
async def update_product_attribute(
    product_id: str, attribute_id: str,
    data: ProductAttributeUpdate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    rows = await db.query(
        "SELECT * FROM product_attribute WHERE product_id = $pid AND attribute_id = $aid LIMIT 1",
        {"pid": product_id, "aid": attribute_id},
    )
    if not rows:
        raise HTTPException(404, ErrorMessages.ATTRIBUTE_ASSIGNMENT_NOT_FOUND.value)
    record_id = str(rows[0]["id"]).split(":")[-1]
    return await db.update("product_attribute", record_id, {"value": data.value})


@router.delete("/products/{product_id}/attributes/{attribute_id}", status_code=204)
async def remove_product_attribute(
    product_id: str, attribute_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    rows = await db.query(
        "SELECT * FROM product_attribute WHERE product_id = $pid AND attribute_id = $aid LIMIT 1",
        {"pid": product_id, "aid": attribute_id},
    )
    if not rows:
        raise HTTPException(404, ErrorMessages.ATTRIBUTE_ASSIGNMENT_NOT_FOUND.value)
    record_id = str(rows[0]["id"]).split(":")[-1]
    await db.delete("product_attribute", record_id)
