"""routers/media.py — §2 Product Images, Files, and Video."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.misc import ImageMetaUpdate, ImageReorder, VideoAttach
from app.core.storage import ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES, save_file, delete_file

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

# ── Images ─────────────────────────────────────────────────────────────────────

@router.post("/{product_id}/images", status_code=201)
async def upload_images(
    product_id: str,
    files: List[UploadFile] = File(...),
    is_primary: bool = Form(False),
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    created = []
    for idx, f in enumerate(files):
        url = await save_file(f, subfolder="products", allowed_types=ALLOWED_IMAGE_TYPES)
        existing_count = await db.count("product_image", f"product_id = '{product_id}'")
        record = await db.create(
            "product_image",
            {
                "product_id": product_id,
                "url": url,
                "alt_text": "",
                "sort_order": existing_count + idx,
                "is_primary": is_primary and idx == 0,
                "created_at": _NOW(),
            },
        )
        created.append(record)
    return created

@router.get("/{product_id}/images")
async def list_images(product_id: str, db: DB = Depends(get_db)):
    return await db.query(
        "SELECT * FROM product_image WHERE product_id = $pid ORDER BY sort_order ASC",
        {"pid": product_id},
    )

@router.patch("/{product_id}/images/{image_id}")
async def update_image(
    product_id: str,
    image_id: str,
    data: ImageMetaUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    img = await db.select_one("product_image", image_id)
    if not img or img.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.IMAGE_NOT_FOUND.value)

    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if data.is_primary:
        # Clear existing primary flag
        await db.query(
            "UPDATE product_image SET is_primary = false WHERE product_id = $pid",
            {"pid": product_id},
        )
    return await db.update("product_image", image_id, payload)

@router.delete("/{product_id}/images/{image_id}", status_code=204)
async def delete_image(
    product_id: str,
    image_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    img = await db.select_one("product_image", image_id)
    if not img or img.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.IMAGE_NOT_FOUND.value)
    delete_file(img.get("url", ""))
    await db.delete("product_image", image_id)

@router.post("/{product_id}/images/reorder")
async def reorder_images(
    product_id: str,
    data: ImageReorder,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    for idx, img_id in enumerate(data.ordered_ids):
        await db.update("product_image", img_id, {"sort_order": idx})
    return {"message": SuccessMessages.IMAGES_REORDERED.value}

# ── Files ──────────────────────────────────────────────────────────────────────

@router.post("/{product_id}/files", status_code=201)
async def upload_file(
    product_id: str,
    file: UploadFile = File(...),
    label: str = Form(""),
    file_type: str = Form("other"),
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    url = await save_file(file, subfolder="product_files")
    record = await db.create(
        "product_file",
        {
            "product_id": product_id,
            "url": url,
            "label": label,
            "file_type": file_type,
            "filename": file.filename,
            "created_at": _NOW(),
        },
    )
    return record

@router.get("/{product_id}/files")
async def list_files(product_id: str, db: DB = Depends(get_db)):
    return await db.query(
        "SELECT * FROM product_file WHERE product_id = $pid", {"pid": product_id}
    )

@router.delete("/{product_id}/files/{file_id}", status_code=204)
async def delete_product_file(
    product_id: str,
    file_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    f = await db.select_one("product_file", file_id)
    if not f or f.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.FILE_NOT_FOUND.value)
    delete_file(f.get("url", ""))
    await db.delete("product_file", file_id)

# ── Video ──────────────────────────────────────────────────────────────────────

@router.post("/{product_id}/video", status_code=201)
async def attach_video(
    product_id: str,
    data: VideoAttach,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    record = await db.create(
        "product_video",
        {
            "product_id": product_id,
            **data.model_dump(),
            "created_at": _NOW(),
        },
    )
    return record

# ── Digital assets (§24) ───────────────────────────────────────────────────────

@router.post("/{product_id}/digital-assets", status_code=201)
async def upload_digital_asset(
    product_id: str,
    file: UploadFile = File(...),
    license_type: str = Form("single"),
    max_downloads: int = Form(3),
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    url = await save_file(file, subfolder="digital_assets")
    record = await db.create(
        "digital_asset",
        {
            "product_id": product_id,
            "file_url": url,
            "filename": file.filename,
            "license_type": license_type,
            "max_downloads": max_downloads,
            "created_at": _NOW(),
        },
    )
    return record

@router.get("/{product_id}/digital-assets")
async def list_digital_assets(product_id: str, db: DB = Depends(get_db)):
    return await db.query(
        "SELECT * FROM digital_asset WHERE product_id = $pid", {"pid": product_id}
    )

@router.delete("/{product_id}/digital-assets/{asset_id}", status_code=204)
async def delete_digital_asset(
    product_id: str,
    asset_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    asset = await db.select_one("digital_asset", asset_id)
    if not asset or asset.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.ASSET_NOT_FOUND.value)
    delete_file(asset.get("file_url", ""))
    await db.delete("digital_asset", asset_id)
