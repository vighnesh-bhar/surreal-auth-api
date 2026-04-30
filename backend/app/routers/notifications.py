"""routers/notifications.py — §18 Restock & Price-drop Notifications."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.misc import AlertTrigger, PriceDropNotify, RestockNotify

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/{product_id}/notify-restock", status_code=201)
async def subscribe_restock(product_id: str, data: RestockNotify, db: DB = Depends(get_db)):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    dup = await db.query(
        "SELECT id FROM notification_sub WHERE product_id = $pid AND email = $email AND type = 'restock' LIMIT 1",
        {"pid": product_id, "email": data.email},
    )
    if dup:
        return {"message": SuccessMessages.ALREADY_SUBSCRIBED.value}
    record = await db.create(
        "notification_sub",
        {"product_id": product_id, "variant_id": data.variant_id,
         "email": data.email, "type": "restock", "created_at": _NOW()},
    )
    return record


@router.delete("/{product_id}/notify-restock", status_code=204)
async def unsubscribe_restock(product_id: str, email: str, db: DB = Depends(get_db)):
    rows = await db.query(
        "SELECT id FROM notification_sub WHERE product_id = $pid AND email = $email AND type = 'restock' LIMIT 1",
        {"pid": product_id, "email": email},
    )
    if rows:
        rid = str(rows[0]["id"]).split(":")[-1]
        await db.delete("notification_sub", rid)


@router.post("/{product_id}/notify-price-drop", status_code=201)
async def subscribe_price_drop(product_id: str, data: PriceDropNotify, db: DB = Depends(get_db)):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    record = await db.create(
        "notification_sub",
        {
            "product_id": product_id,
            "variant_id": data.variant_id,
            "email": data.email,
            "type": "price_drop",
            "target_price": data.target_price,
            "created_at": _NOW(),
        },
    )
    return record


@router.post("/alerts/trigger")
async def trigger_alert(
    data: AlertTrigger,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    """Trigger notification emails. Wire up SendGrid/Resend to send real emails."""
    subs = await db.query(
        "SELECT * FROM notification_sub WHERE product_id = $pid AND type = $type",
        {"pid": data.product_id, "type": data.alert_type},
    )
    return {
        "message": f"Triggered {data.alert_type} alert",
        "recipients": len(subs),
        "note": "Wire up SendGrid/Resend here to send real emails",
    }
