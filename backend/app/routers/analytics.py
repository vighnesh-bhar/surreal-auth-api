"""routers/analytics.py — §19 Analytics & Reporting."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_admin
from app.db.surreal import DB, get_db

router = APIRouter()


@router.get("/products/top-selling")
async def top_selling(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
    metric: Literal["revenue", "units"] = "revenue",
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    date_filter = ""
    if from_date:
        date_filter += f" AND created_at >= '{from_date}'"
    if to_date:
        date_filter += f" AND created_at <= '{to_date}'"

    if metric == "units":
        rows = await db.query(
            f"SELECT product_id, math::sum(quantity) AS total_units "
            f"FROM order_item WHERE 1=1 {date_filter} "
            f"GROUP BY product_id ORDER BY total_units DESC LIMIT {limit}"
        )
    else:
        rows = await db.query(
            f"SELECT product_id, math::sum(subtotal) AS total_revenue "
            f"FROM order_item WHERE 1=1 {date_filter} "
            f"GROUP BY product_id ORDER BY total_revenue DESC LIMIT {limit}"
        )
    return rows


@router.get("/products/views")
async def product_views(
    product_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    granularity: Literal["day", "week", "month"] = "day",
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    conditions = []
    if product_id:
        conditions.append(f"product_id = '{product_id}'")
    if from_date:
        conditions.append(f"created_at >= '{from_date}'")
    if to_date:
        conditions.append(f"created_at <= '{to_date}'")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await db.query(
        f"SELECT product_id, time::floor(created_at, 1{granularity[0]}) AS period, count() AS views "
        f"FROM product_view {where} GROUP BY product_id, period ORDER BY period ASC"
    )
    return rows


@router.get("/products/conversion")
async def conversion_funnel(
    product_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    date_f = ""
    if from_date:
        date_f += f" AND created_at >= '{from_date}'"
    if to_date:
        date_f += f" AND created_at <= '{to_date}'"
    pid_f = f" AND product_id = '{product_id}'" if product_id else ""

    def rate(num: int, den: int) -> float:
        return round(num / den * 100, 2) if den else 0.0

    # Views
    v_rows = await db.query(
        f"SELECT product_id, count() AS views FROM product_view WHERE 1=1 {pid_f} {date_f} GROUP BY product_id"
    )
    # Cart adds
    c_rows = await db.query(
        f"SELECT product_id, count() AS cart_adds FROM cart_item WHERE 1=1 {pid_f} GROUP BY product_id"
    )
    # Purchases (exclude cancelled/refunded)
    p_rows = await db.query(
        f"SELECT oi.product_id AS product_id, math::sum(oi.quantity) AS purchases "
        f"FROM order_item AS oi WHERE 1=1 {pid_f} GROUP BY product_id"
    )

    # Index by product_id for easy merging
    views_map    = {r["product_id"]: r["views"]     for r in v_rows}
    cart_map     = {r["product_id"]: r["cart_adds"] for r in c_rows}
    purchase_map = {r["product_id"]: r["purchases"] for r in p_rows}
    all_pids     = set(views_map) | set(cart_map) | set(purchase_map)

    if product_id:
        all_pids = {product_id}

    result = []
    for pid in all_pids:
        v = views_map.get(pid, 0)
        c = cart_map.get(pid, 0)
        p = purchase_map.get(pid, 0)
        result.append({
            "product_id": pid,
            "views": v,
            "cart_adds": c,
            "purchases": p,
            "view_to_cart_rate": rate(c, v),
            "cart_to_purchase_rate": rate(p, c),
            "overall_conversion": rate(p, v),
        })

    return result[0] if (product_id and result) else result


@router.get("/inventory/turnover")
async def inventory_turnover(
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    """Days-of-stock and inventory turnover rate per product."""
    rows = await db.query(
        "SELECT product_id, "
        "   math::sum(quantity) AS total_sold, "
        "   math::mean(stock) AS avg_stock "
        "FROM order_item GROUP BY product_id"
    )
    results = []
    for r in rows:
        sold = r.get("total_sold", 0)
        avg_stock = r.get("avg_stock", 0)
        turnover = round(sold / avg_stock, 2) if avg_stock else 0
        days_of_stock = round(avg_stock / (sold / 365), 1) if sold else 999
        results.append({
            "product_id": r["product_id"],
            "total_sold": sold,
            "avg_stock": avg_stock,
            "turnover_rate": turnover,
            "days_of_stock": days_of_stock,
        })
    return results


@router.get("/reviews/sentiment")
async def review_sentiment(
    product_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    conditions = ["status = 'approved'"]
    if product_id:
        conditions.append(f"product_id = '{product_id}'")
    if from_date:
        conditions.append(f"created_at >= '{from_date}'")
    if to_date:
        conditions.append(f"created_at <= '{to_date}'")

    where = "WHERE " + " AND ".join(conditions)
    rows = await db.query(
        f"SELECT product_id, math::mean(rating) AS avg_rating, count() AS total "
        f"FROM review {where} GROUP BY product_id"
    )
    # Classify sentiment buckets
    for r in rows:
        avg = r.get("avg_rating", 0)
        r["sentiment"] = "positive" if avg >= 4 else "neutral" if avg >= 3 else "negative"
    return rows


@router.get("/products/revenue")
async def revenue_breakdown(
    group_by: Literal["product", "category", "brand"] = "product",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: DB = Depends(get_db),
    _admin: dict = Depends(get_current_admin),
):
    date_filter = ""
    if from_date:
        date_filter += f" AND oi.created_at >= '{from_date}'"
    if to_date:
        date_filter += f" AND oi.created_at <= '{to_date}'"

    if group_by == "product":
        rows = await db.query(
            f"SELECT product_id, math::sum(subtotal) AS revenue "
            f"FROM order_item WHERE 1=1 {date_filter} "
            f"GROUP BY product_id ORDER BY revenue DESC"
        )
    else:
        # JOIN-style: fetch product data and group by category/brand
        rows = await db.query(
            f"SELECT p.{group_by}_id AS group_key, math::sum(oi.subtotal) AS revenue "
            f"FROM order_item AS oi, product AS p "
            f"WHERE oi.product_id = p.id {date_filter} "
            f"GROUP BY group_key ORDER BY revenue DESC"
        )
    return rows
