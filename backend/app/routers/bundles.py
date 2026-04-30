"""routers/bundles.py — §14 Bundles & Kits."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import BundleCreate, BundleUpdate
from app.models.common import strip_none

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/bundles", status_code=201)
async def create_bundle(
    data: BundleCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)
):
    record = await db.create("bundle", {**data.model_dump(), "created_at": _NOW(), "updated_at": _NOW()})
    return record


@router.get("/bundles")
async def list_bundles(db: DB = Depends(get_db)):
    return await db.query("SELECT * FROM bundle ORDER BY created_at DESC")


@router.patch("/bundles/{bundle_id}")
async def update_bundle(
    bundle_id: str, data: BundleUpdate,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    payload = strip_none(data.model_dump())
    payload["updated_at"] = _NOW()
    updated = await db.update("bundle", bundle_id, payload)
    if not updated:
        raise HTTPException(404, ErrorMessages.BUNDLE_NOT_FOUND.value)
    return updated


@router.delete("/bundles/{bundle_id}", status_code=204)
async def delete_bundle(
    bundle_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    ok = await db.delete("bundle", bundle_id)
    if not ok:
        raise HTTPException(404, ErrorMessages.BUNDLE_NOT_FOUND.value)
