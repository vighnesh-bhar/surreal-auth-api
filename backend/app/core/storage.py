"""storage.py — File upload/delete. Saves to local disk under MEDIA_DIR.
To use S3/R2: swap save_file() and delete_file() with boto3 calls."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile

from app.core.config import settings

MEDIA_ROOT = Path(settings.MEDIA_DIR)
MAX_BYTES  = settings.MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_FILE_TYPES  = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES | {
    "application/pdf", "application/zip", "application/octet-stream", "text/csv",
}

_EXT_MAP = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "video/mp4": ".mp4", "video/webm": ".webm", "application/pdf": ".pdf", "text/csv": ".csv",
}


async def save_file(upload: UploadFile, subfolder: str = "misc", allowed_types: set[str] = None) -> str:
    """Persist a file upload; returns the public URL path e.g. '/media/products/abc.jpg'."""
    ct = upload.content_type or "application/octet-stream"
    allowed = allowed_types or ALLOWED_FILE_TYPES

    if ct not in allowed:
        raise HTTPException(415, f"Unsupported file type: {ct}")

    data = await upload.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")

    ext  = Path(upload.filename or "file").suffix or _EXT_MAP.get(ct, ".bin")
    dest = MEDIA_ROOT / subfolder / f"{uuid.uuid4().hex}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(dest, "wb") as f:
        await f.write(data)

    return f"/{settings.MEDIA_DIR}/{subfolder}/{dest.name}"


def delete_file(url_path: str) -> None:
    """Delete a previously saved file. Silently ignores missing files."""
    if url_path:
        try:
            Path(url_path.lstrip("/")).unlink(missing_ok=True)
        except OSError:
            pass
