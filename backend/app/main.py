"""main.py — Unified FastAPI app (Auth + Product APIs)"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.surreal import connect_db, disconnect_db

# Routers
from app.routers.auth_router import router as auth_router
from app.routers.products import router as products_router
from app.routers.media import router as media_router
from app.routers.variants import router as variants_router
from app.routers.inventory import router as inventory_router
from app.routers.pricing import router as pricing_router
from app.routers.categories import router as categories_router
from app.routers.attributes import router as attributes_router
from app.routers.search import router as search_router
from app.routers.cart import router as cart_router
from app.routers.wishlist import router as wishlist_router
from app.routers.reviews import router as reviews_router
from app.routers.qa import router as qa_router
from app.routers.orders import router as orders_router
from app.routers.bundles import router as bundles_router
from app.routers.compare import router as compare_router
from app.routers.brands import router as brands_router
from app.routers.tags import router as tags_router
from app.routers.notifications import router as notifications_router
from app.routers.analytics import router as analytics_router
from app.routers.bulk import router as bulk_router
from app.routers.coupons import router as coupons_router


# ✅ Lifespan replaces old @app.on_event("startup")
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()  # Async DB connect
    Path(settings.MEDIA_DIR).mkdir(parents=True, exist_ok=True)
    yield
    await disconnect_db()  # Clean shutdown


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

# ✅ CORS (merge both configs cleanly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # from config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR, check_dir=False), name="media")

# Prefix
P = settings.API_PREFIX

# ✅ Routers (INCLUDING AUTH)
# New API surface
app.include_router(auth_router, prefix=f"{P}/auth", tags=["Auth"])
# Legacy paths used by the frontend
app.include_router(auth_router, prefix="/auth", tags=["Auth (legacy)"])

# Product system
app.include_router(products_router,      prefix=f"{P}/products", tags=["Products"])
app.include_router(media_router,         prefix=f"{P}/products", tags=["Media"])
app.include_router(variants_router,      prefix=f"{P}/products", tags=["Variants"])
app.include_router(inventory_router,     prefix=f"{P}/products", tags=["Inventory"])
app.include_router(pricing_router,       prefix=f"{P}",          tags=["Pricing"])
app.include_router(categories_router,    prefix=f"{P}",          tags=["Categories"])
app.include_router(attributes_router,    prefix=f"{P}",          tags=["Attributes"])
app.include_router(search_router,        prefix=f"{P}/products", tags=["Search"])
app.include_router(cart_router,          prefix=f"{P}/cart",     tags=["Cart"])
app.include_router(wishlist_router,      prefix=f"{P}/wishlist", tags=["Wishlist"])
app.include_router(reviews_router,       prefix=f"{P}",          tags=["Reviews"])
app.include_router(qa_router,            prefix=f"{P}",          tags=["Q&A"])
app.include_router(orders_router,        prefix=f"{P}/orders",   tags=["Orders"])
app.include_router(bundles_router,       prefix=f"{P}/products", tags=["Bundles"])
app.include_router(compare_router,       prefix=f"{P}/products", tags=["Compare"])
app.include_router(brands_router,        prefix=f"{P}/brands",   tags=["Brands"])
app.include_router(tags_router,          prefix=f"{P}",          tags=["Tags"])
app.include_router(notifications_router, prefix=f"{P}/products", tags=["Notifications"])
app.include_router(analytics_router,     prefix=f"{P}/analytics",tags=["Analytics"])
app.include_router(bulk_router,          prefix=f"{P}/products", tags=["Bulk"])
app.include_router(coupons_router,       prefix=f"{P}/coupons",  tags=["Coupons"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}