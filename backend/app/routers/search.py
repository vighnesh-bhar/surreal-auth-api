"""routers/search.py — §8 Search & Discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import optional_user
from app.db.surreal import DB, get_db
from app.models.misc import ProductViewEvent

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.get("/search")
async def search_products(
    q: str = Query(""),
    category_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    tags: Optional[str] = None,           # CSV: "sale,new"
    in_stock: Optional[bool] = None,
    sort_by: str = "created_at",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: DB = Depends(get_db),
):
    conditions = ["status = 'active'"]

    if q:
        # SurrealDB full-text: use string::contains for now; upgrade to full-text index later
        conditions.append(f"(string::contains(string::lowercase(name), '{q.lower()}') OR string::contains(string::lowercase(description), '{q.lower()}'))")
    if category_id:
        conditions.append(f"category_id = '{category_id}'")
    if brand_id:
        conditions.append(f"brand_id = '{brand_id}'")
    if min_price is not None:
        conditions.append(f"price >= {min_price}")
    if max_price is not None:
        conditions.append(f"price <= {max_price}")
    if tags:
        for tag in tags.split(","):
            t = tag.strip()
            conditions.append(f"'{t}' IN tags")
    if in_stock:
        conditions.append("stock > 0")

    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * limit

    items = await db.query(
        f"SELECT * FROM product {where} ORDER BY {sort_by} DESC LIMIT {limit} START {offset}"
    )
    total = await db.count("product", " AND ".join(conditions))
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/filter")
async def faceted_filter(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: DB = Depends(get_db),
):
    # Build base conditions (applied to product query)
    base = ["status = 'active'"]
    if q:
        base.append(f"string::contains(string::lowercase(name), '{q.lower()}')")
    if category_id:
        base.append(f"category_id = '{category_id}'")
    if brand_id:
        base.append(f"brand_id = '{brand_id}'")
    if min_price is not None:
        base.append(f"price >= {min_price}")
    if max_price is not None:
        base.append(f"price <= {max_price}")
    if in_stock:
        base.append("stock > 0")

    where = "WHERE " + " AND ".join(base)
    offset = (page - 1) * limit

    products = await db.query(
        f"SELECT * FROM product {where} ORDER BY created_at DESC LIMIT {limit} START {offset}"
    )
    total = await db.count("product", " AND ".join(base))

    # Category facets — all filters EXCEPT category active
    cat_base = [c for c in base if "category_id" not in c]
    cat_where = ("WHERE " + " AND ".join(cat_base)) if cat_base else ""
    cat_facets = await db.query(
        f"SELECT category_id, count() AS n FROM product {cat_where} GROUP BY category_id"
    )

    # Brand facets — all filters EXCEPT brand active
    brand_base = [c for c in base if "brand_id" not in c]
    brand_where = ("WHERE " + " AND ".join(brand_base)) if brand_base else ""
    brand_facets = await db.query(
        f"SELECT brand_id, count() AS n FROM product {brand_where} GROUP BY brand_id"
    )

    # Price range facets
    price_base = [c for c in base if "price" not in c]
    price_buckets = [
        ("$0–$25", 0, 25), ("$25–$50", 25, 50),
        ("$50–$100", 50, 100), ("$100+", 100, 9_999_999),
    ]
    price_facets = []
    for label, lo, hi in price_buckets:
        conds = price_base + [f"price >= {lo}", f"price < {hi}"]
        cnt = await db.count("product", " AND ".join(conds))
        price_facets.append({"label": label, "min": lo, "max": hi, "count": cnt})

    return {
        "products": products,
        "total": total,
        "page": page,
        "limit": limit,
        "facets": {
            "categories": cat_facets,
            "brands": brand_facets,
            "price_ranges": price_facets,
        },
    }


@router.get("/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    db: DB = Depends(get_db),
):
    rows = await db.query(
        f"SELECT id, name FROM product WHERE status = 'active' "
        f"AND string::contains(string::lowercase(name), '{q.lower()}') "
        f"LIMIT {limit}"
    )
    return [{"id": r["id"], "name": r["name"]} for r in rows]


@router.get("/related/{product_id}")
async def related_products(
    product_id: str,
    limit: int = Query(6, ge=1, le=20),
    db: DB = Depends(get_db),
):
    product = await db.query(
        "SELECT category_id, tags FROM product WHERE id = $pid LIMIT 1",
        {"pid": f"product:{product_id}"},
    )
    if not product:
        return []
    p = product[0]
    category = p.get("category_id", "")
    tags = p.get("tags", [])

    rows = await db.query(
        f"SELECT * FROM product WHERE status = 'active' "
        f"AND id != product:{product_id} "
        f"AND (category_id = '{category}') "
        f"LIMIT {limit}"
    )
    return rows


@router.get("/trending")
async def trending_products(
    limit: int = Query(10, ge=1, le=50),
    db: DB = Depends(get_db),
):
    # Trending = most-viewed in last 7 days
    rows = await db.query(
        f"SELECT product_id, count() AS view_count FROM product_view "
        f"WHERE created_at > time::now() - 7d "
        f"GROUP BY product_id ORDER BY view_count DESC LIMIT {limit}"
    )
    return rows


@router.get("/recently-viewed")
async def recently_viewed(
    user_id: str = Depends(optional_user),
    limit: int = Query(10),
    db: DB = Depends(get_db),
):
    if not user_id:
        return []
    rows = await db.query(
        f"SELECT product_id, max(created_at) AS last_viewed FROM product_view "
        f"WHERE user_id = '{user_id}' "
        f"GROUP BY product_id ORDER BY last_viewed DESC LIMIT {limit}"
    )
    return rows


@router.post("/{product_id}/view", status_code=201)
async def log_view(product_id: str, data: ProductViewEvent, db: DB = Depends(get_db)):
    record = await db.create(
        "product_view",
        {"product_id": product_id, **data.model_dump(), "created_at": _NOW()},
    )
    return record
