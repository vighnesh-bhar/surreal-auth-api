"""routers/wishlist.py — §10 Wishlist & Saved Items."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_admin, get_current_user
from app.core.messages import ErrorMessages
from app.db.surreal import DB, get_db
from app.models.misc import WishlistCreate, WishlistItemAdd, WishlistMoveToCart

router = APIRouter()
_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


@router.post("/", status_code=201)
async def create_wishlist(data: WishlistCreate, db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    record = await db.create(
        "wishlist",
        {"user_id": _user["id"], **data.model_dump(), "created_at": _NOW()},
    )
    return record


@router.get("/")
async def list_wishlists(db: DB = Depends(get_db), _user: dict = Depends(get_current_user)):
    return await db.query(
        "SELECT * FROM wishlist WHERE user_id = $uid", {"uid": _user["id"]}
    )


@router.post("/{wishlist_id}/items", status_code=201)
async def add_to_wishlist(
    wishlist_id: str, data: WishlistItemAdd,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    wl = await db.select_one("wishlist", wishlist_id)
    if not wl or wl["user_id"] != _user["id"]:
        raise HTTPException(404, ErrorMessages.WISHLIST_NOT_FOUND.value)

    existing = await db.query(
        "SELECT id FROM wishlist_item WHERE wishlist_id = $wid AND product_id = $pid LIMIT 1",
        {"wid": wishlist_id, "pid": data.product_id},
    )
    if existing:
        raise HTTPException(409, ErrorMessages.PRODUCT_ALREADY_IN_WISHLIST.value)

    record = await db.create(
        "wishlist_item",
        {"wishlist_id": wishlist_id, **data.model_dump(), "created_at": _NOW()},
    )
    return record


@router.delete("/{wishlist_id}/items/{item_id}", status_code=204)
async def remove_from_wishlist(
    wishlist_id: str, item_id: str,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    item = await db.select_one("wishlist_item", item_id)
    if not item or item["wishlist_id"] != wishlist_id:
        raise HTTPException(404, ErrorMessages.ITEM_NOT_FOUND.value)
    await db.delete("wishlist_item", item_id)


@router.post("/{wishlist_id}/move-to-cart")
async def move_to_cart(
    wishlist_id: str, data: WishlistMoveToCart,
    db: DB = Depends(get_db), _user: dict = Depends(get_current_user),
):
    cart = await db.select_one("cart", data.cart_id)
    if not cart:
        raise HTTPException(404, ErrorMessages.CART_NOT_FOUND.value)

    moved = []
    for item_id in data.item_ids:
        item = await db.select_one("wishlist_item", item_id)
        if not item:
            continue
        product = await db.select_one("product", item["product_id"])
        if not product:
            continue
        unit_price = product.get("price", 0.0)
        await db.create(
            "cart_item",
            {
                "cart_id": data.cart_id,
                "product_id": item["product_id"],
                "variant_id": item.get("variant_id"),
                "quantity": 1,
                "unit_price": unit_price,
                "subtotal": unit_price,
                "created_at": _NOW(),
                "updated_at": _NOW(),
            },
        )
        await db.delete("wishlist_item", item_id)
        moved.append(item_id)
    return {"moved_items": moved, "cart_id": data.cart_id}


@router.get("/{wishlist_id}/share")
async def share_wishlist(
    wishlist_id: str,
    db: DB = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    wl = await db.select_one("wishlist", wishlist_id)
    if not wl:
        raise HTTPException(404, ErrorMessages.WISHLIST_NOT_FOUND.value)
    if not wl.get("is_public"):
        raise HTTPException(403, ErrorMessages.WISHLIST_PRIVATE.value)
    return {"share_url": f"/wishlists/{wishlist_id}/public"}
