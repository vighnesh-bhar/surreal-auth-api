"""routers/pricing.py — §5 Pricing & Discounts."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import BulkPriceUpdate, DiscountCreate, PriceUpdate, PricingRuleCreate

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.patch("/products/{product_id}/price")
async def update_price(
    product_id: str,
    data: PriceUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    updated = await db.update(
        "product",
        product_id,
        {"price": data.price, "compare_at_price": data.compare_at_price,
         "currency": data.currency, "updated_at": _NOW()},
    )
    return updated


@router.post("/products/{product_id}/discounts", status_code=201)
async def create_discount(
    product_id: str,
    data: DiscountCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    p = await db.select_one("product", product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)
    record = await db.create(
        "discount",
        {"product_id": product_id, **data.model_dump(), "is_active": True, "created_at": _NOW()},
    )
    return record


@router.get("/products/{product_id}/discounts")
async def list_discounts(product_id: str, db: DB = Depends(get_db)):
    return await db.query(
        "SELECT * FROM discount WHERE product_id = $pid AND is_active = true",
        {"pid": product_id},
    )


@router.delete("/products/{product_id}/discounts/{discount_id}", status_code=204)
async def delete_discount(
    product_id: str,
    discount_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    d = await db.select_one("discount", discount_id)
    if not d or d.get("product_id") != product_id:
        raise HTTPException(404, ErrorMessages.DISCOUNT_NOT_FOUND.value)
    await db.update("discount", discount_id, {"is_active": False})


@router.post("/products/{product_id}/price/bulk-update")
async def bulk_price_update(
    product_id: str,
    data: BulkPriceUpdate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    results = []
    for u in data.updates:
        vid = u.get("variant_id")
        price = u.get("price")
        v = await db.select_one("variant", vid)
        if not v or v.get("product_id") != product_id:
            results.append({"variant_id": vid, "error": "Not found"})
            continue
        updated = await db.update("variant", vid, {"price": price, "updated_at": _NOW()})
        results.append({"variant_id": vid, "new_price": price})
    return results


@router.post("/pricing/rules", status_code=201)
async def create_pricing_rule(
    data: PricingRuleCreate,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    # Validate product exists
    p = await db.select_one("product", data.product_id)
    if not p:
        raise HTTPException(404, ErrorMessages.PRODUCT_NOT_FOUND.value)

    # Validate tier structure
    if data.rule_type in ("volume", "tiered"):
        if not data.tiers:
            raise HTTPException(422, ErrorMessages.TIERS_REQUIRED.value)
        for tier in data.tiers:
            if "min_qty" not in tier or "price" not in tier:
                raise HTTPException(422, ErrorMessages.TIER_FIELDS_REQUIRED.value)
            if tier["price"] < 0:
                raise HTTPException(422, ErrorMessages.TIER_PRICE_NEGATIVE.value)
        # Ensure ascending order
        sorted_tiers = sorted(data.tiers, key=lambda t: t["min_qty"])
        if sorted_tiers != data.tiers:
            raise HTTPException(422, ErrorMessages.TIERS_SORTED_ASC.value)

    # Check for conflicting active rule of same type
    existing = await db.query(
        "SELECT id FROM pricing_rule WHERE product_id = $pid AND rule_type = $rt AND is_active = true LIMIT 1",
        {"pid": data.product_id, "rt": data.rule_type},
    )
    if existing:
        raise HTTPException(409, ErrorMessages.ACTIVE_RULE_EXISTS.value.format(rule_type=data.rule_type))

    rule = await db.create(
        "pricing_rule",
        {
            "product_id": data.product_id,
            "rule_type": data.rule_type,
            "tiers": data.tiers,
            "is_active": True,
            "created_by": _user["id"],
            "created_at": _NOW(),
        },
    )
    return rule
