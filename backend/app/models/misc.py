"""
models/misc.py — schemas for all smaller domain areas:
  brands, categories, collections, tags, attributes,
  pricing rules, discounts, bundles, coupons, wishlists,
  notifications, digital assets, user auth.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, EmailStr

# ── Auth ───────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = ""
    role: Literal["user", "admin"] = "user"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

# ── Brands ─────────────────────────────────────────────────────────────────────

class BrandCreate(BaseModel):
    name: str
    description: str = ""
    website: Optional[str] = None
    slug: str

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None

# ── Categories ─────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None
    description: str = ""
    slug: str
    image: Optional[str] = None

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None

class CategoryProductAssign(BaseModel):
    product_id: str

# ── Collections ────────────────────────────────────────────────────────────────

class CollectionRule(BaseModel):
    field: str          # "tags", "price", "brand"
    operator: str       # "contains", "gt", "lt", "eq"
    value: Any

class CollectionCreate(BaseModel):
    name: str
    description: str = ""
    is_automated: bool = False
    rules: list[CollectionRule] = []
    product_ids: list[str] = []

class CollectionProductAdd(BaseModel):
    product_id: str

# ── Attributes ─────────────────────────────────────────────────────────────────

class AttributeCreate(BaseModel):
    name: str
    type: Literal["text", "number", "boolean", "select", "multi-select"]
    options: list[str] = []
    unit: str = ""

class ProductAttributeAssign(BaseModel):
    attributes: list[dict]   # [{"attribute_id": ..., "value": ...}]

class ProductAttributeUpdate(BaseModel):
    value: Any

# ── Tags ───────────────────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str
    color: str = "#6366f1"

class ProductTagsAssign(BaseModel):
    tags: list[str]

# ── Discounts ──────────────────────────────────────────────────────────────────

class DiscountCreate(BaseModel):
    type: Literal["percentage", "fixed"]
    value: float = Field(..., ge=0)
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    label: str = ""

class PriceUpdate(BaseModel):
    price: float = Field(..., ge=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    currency: str = "USD"

class BulkPriceUpdate(BaseModel):
    updates: list[dict]   # [{"variant_id": ..., "price": ...}]

class PricingRuleCreate(BaseModel):
    product_id: str
    rule_type: Literal["volume", "tiered", "bundle"]
    tiers: list[dict]    # [{"min_qty": 5, "price": 9.99}]

# ── Bundles ────────────────────────────────────────────────────────────────────

class BundleCreate(BaseModel):
    name: str
    description: str = ""
    product_ids: list[str]
    bundle_price: float = Field(..., ge=0)
    discount_type: Literal["percentage", "fixed"] = "fixed"
    discount_value: float = 0

class BundleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    product_ids: Optional[list[str]] = None
    bundle_price: Optional[float] = None
    discount_value: Optional[float] = None

# ── Coupons ────────────────────────────────────────────────────────────────────

class CouponCreate(BaseModel):
    code: str
    type: Literal["percentage", "fixed", "free_shipping"]
    value: float = Field(0, ge=0)
    min_order_value: float = 0
    applies_to: Literal["all", "products", "categories"] = "all"
    product_ids: list[str] = []
    category_ids: list[str] = []
    usage_limit: Optional[int] = None
    per_user_limit: int = 1
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None

class CouponValidate(BaseModel):
    code: str
    cart_id: str

# ── Wishlists ──────────────────────────────────────────────────────────────────

class WishlistCreate(BaseModel):
    name: str = "My Wishlist"
    is_public: bool = False

class WishlistItemAdd(BaseModel):
    product_id: str
    variant_id: Optional[str] = None

class WishlistMoveToCart(BaseModel):
    item_ids: list[str]
    cart_id: str

# ── Notifications ──────────────────────────────────────────────────────────────

class RestockNotify(BaseModel):
    email: EmailStr
    variant_id: Optional[str] = None

class PriceDropNotify(BaseModel):
    email: EmailStr
    target_price: float = Field(..., ge=0)
    variant_id: Optional[str] = None

class AlertTrigger(BaseModel):
    product_id: str
    alert_type: Literal["restock", "price_drop"]

# ── Comparison ─────────────────────────────────────────────────────────────────

class CompareCreate(BaseModel):
    product_ids: list[str] = Field(..., min_length=2)

class CompareAdd(BaseModel):
    product_id: str

# ── Video attachment ───────────────────────────────────────────────────────────

class VideoAttach(BaseModel):
    url: str
    source: Literal["youtube", "vimeo", "upload"]
    label: str = ""

# ── Image reorder ──────────────────────────────────────────────────────────────

class ImageReorder(BaseModel):
    ordered_ids: list[str]

class ImageMetaUpdate(BaseModel):
    alt_text: Optional[str] = None
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None

# ── Digital assets ─────────────────────────────────────────────────────────────

class DigitalAssetResponse(BaseModel):
    id: str
    product_id: str
    file_url: str
    license_type: str
    max_downloads: int

# ── Product view event ─────────────────────────────────────────────────────────

class ProductViewEvent(BaseModel):
    session_id: str
    user_id: Optional[str] = None
