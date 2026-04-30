"""routers/brands.py — §16 Brands."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from typing import Optional

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import BrandCreate, BrandUpdate
from app.models.common import strip_none
from app.core.storage import ALLOWED_IMAGE_TYPES, save_file

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def create_brand(
    name: str = Form(...),
    description: str = Form(""),
    website: Optional[str] = Form(None),
    slug: str = Form(...),
    logo: Optional[UploadFile] = File(None),
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    dup = await db.query("SELECT id FROM brand WHERE slug = $slug LIMIT 1", {"slug": slug})
    if dup:
        raise HTTPException(409, ErrorMessages.BRAND_SLUG_EXISTS.value)

    logo_url = None
    if logo:
        logo_url = await save_file(logo, subfolder="brands", allowed_types=ALLOWED_IMAGE_TYPES)

    record = await db.create(
        "brand",
        {"name": name, "description": description, "website": website,
         "slug": slug, "logo_url": logo_url, "created_at": _NOW()},
    )
    return record


@router.get("/")
async def list_brands(db: DB = Depends(get_db)):
    return await db.query("SELECT * FROM brand ORDER BY name ASC")


@router.patch("/{brand_id}")
async def update_brand(
    brand_id: str, data: BrandUpdate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    updated = await db.update("brand", brand_id, strip_none(data.model_dump()))
    if not updated:
        raise HTTPException(404, ErrorMessages.BRAND_NOT_FOUND.value)
    return updated


@router.delete("/{brand_id}", status_code=204)
async def delete_brand(
    brand_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    ok = await db.delete("brand", brand_id)
    if not ok:
        raise HTTPException(404, ErrorMessages.BRAND_NOT_FOUND.value)


@router.get("/{brand_id}/products")
async def brand_products(brand_id: str, db: DB = Depends(get_db)):
    b = await db.select_one("brand", brand_id)
    if not b:
        raise HTTPException(404, ErrorMessages.BRAND_NOT_FOUND.value)
    return await db.query(
        "SELECT * FROM product WHERE brand_id = $bid AND status = 'active'",
        {"bid": brand_id},
    )
