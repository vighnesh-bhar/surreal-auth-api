"""routers/reviews.py — §11 Reviews & Ratings."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.models.review import ReviewCreate, ReviewModerate, ReviewReport, ReviewUpdate, RatingSummary
from app.models.common import strip_none

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/products/{product_id}/reviews", status_code=201)
async def submit_review(
    product_id: str,
    data: ReviewCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    existing = await db.query(
        "SELECT id FROM review WHERE product_id = $pid AND user_id = $uid LIMIT 1",
        {"pid": product_id, "uid": _user["id"]},
    )
    if existing:
        raise HTTPException(409, ErrorMessages.REVIEW_ALREADY_EXISTS.value)

    record = await db.create(
        "review",
        {
            "product_id": product_id,
            "user_id": _user["id"],
            **data.model_dump(),
            "status": "approved",       # auto-approve; change to 'pending' if moderated
            "helpful_count": 0,
            "created_at": _NOW(),
        },
    )
    return record


@router.get("/products/{product_id}/reviews")
async def list_reviews(
    product_id: str,
    sort_by: str = Query("newest", pattern="newest|highest|lowest"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: DB = Depends(get_db),
):
    order_map = {"newest": "created_at DESC", "highest": "rating DESC", "lowest": "rating ASC"}
    order = order_map.get(sort_by, "created_at DESC")
    offset = (page - 1) * limit

    rows = await db.query(
        f"SELECT * FROM review WHERE product_id = '{product_id}' AND status = 'approved' "
        f"ORDER BY {order} LIMIT {limit} START {offset}"
    )
    total = await db.count("review", f"product_id = '{product_id}' AND status = 'approved'")
    return {"items": rows, "total": total, "page": page, "limit": limit}


@router.patch("/reviews/{review_id}")
async def edit_review(
    review_id: str,
    data: ReviewUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    review = await db.select_one("review", review_id)
    if not review:
        raise HTTPException(404, ErrorMessages.REVIEW_NOT_FOUND.value)
    if review["user_id"] != _user["id"]:
        raise HTTPException(403, ErrorMessages.CANNOT_EDIT_OTHER_REVIEW.value)
    return await db.update("review", review_id, strip_none(data.model_dump()))


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(
    review_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    review = await db.select_one("review", review_id)
    if not review:
        raise HTTPException(404, ErrorMessages.REVIEW_NOT_FOUND.value)
    if review["user_id"] != _user["id"] and _user.get("role") != "admin":
        raise HTTPException(403, ErrorMessages.FORBIDDEN.value)
    await db.delete("review", review_id)


@router.post("/reviews/{review_id}/helpful")
async def mark_helpful(review_id: str, db: DB = Depends(get_db)):
    review = await db.select_one("review", review_id)
    if not review:
        raise HTTPException(404, ErrorMessages.REVIEW_NOT_FOUND.value)
    count = review.get("helpful_count", 0) + 1
    await db.update("review", review_id, {"helpful_count": count})
    return {"helpful_count": count}


@router.post("/reviews/{review_id}/report")
async def report_review(review_id: str, data: ReviewReport, db: DB = Depends(get_db)):
    review = await db.select_one("review", review_id)
    if not review:
        raise HTTPException(404, ErrorMessages.REVIEW_NOT_FOUND.value)
    await db.create(
        "review_report",
        {"review_id": review_id, "reason": data.reason, "created_at": _NOW()},
    )
    return {"message": SuccessMessages.REPORT_SUBMITTED.value}


@router.patch("/reviews/{review_id}/moderate")
async def moderate_review(
    review_id: str,
    data: ReviewModerate,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    review = await db.select_one("review", review_id)
    if not review:
        raise HTTPException(404, ErrorMessages.REVIEW_NOT_FOUND.value)
    return await db.update("review", review_id, {"status": data.status})


@router.get("/products/{product_id}/rating-summary")
async def rating_summary(product_id: str, db: DB = Depends(get_db)):
    rows = await db.query(
        "SELECT rating, count() AS cnt FROM review "
        "WHERE product_id = $pid AND status = 'approved' "
        "GROUP BY rating",
        {"pid": product_id},
    )
    distribution = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    total = 0
    total_score = 0
    for r in rows:
        star = str(r.get("rating", 0))
        cnt = r.get("cnt", 0)
        distribution[star] = cnt
        total += cnt
        total_score += r["rating"] * cnt

    average = round(total_score / total, 2) if total else 0.0
    return {
        "product_id": product_id,
        "average": average,
        "total": total,
        "distribution": distribution,
    }
