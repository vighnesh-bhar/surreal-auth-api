"""Unit tests for /products routes."""

import pytest

PRODUCT = {
    "id": "prod1",
    "name": "Test Widget",
    "sku": "SKU-001",
    "price": 29.99,
    "status": "active",
    "lifecycle_status": "active",
    "locked": False,
    "created_by": "user1",
}


# ── POST /products/ ───────────────────────────────────────────────────────────


def test_create_product_success(user_client, mock_db):
    mock_db.query.return_value = []  # no duplicate SKU
    mock_db.create.return_value = {**PRODUCT, "lifecycle_status": "draft"}

    resp = user_client.post("/api/v1/products/", json={
        "name": "Test Widget",
        "sku": "SKU-001",
        "price": 29.99,
    })
    assert resp.status_code == 201
    assert resp.json()["sku"] == "SKU-001"


def test_create_product_duplicate_sku_returns_409(user_client, mock_db):
    mock_db.query.return_value = [{"id": "existing"}]  # SKU taken

    resp = user_client.post("/api/v1/products/", json={
        "name": "Widget",
        "sku": "SKU-001",
        "price": 10.0,
    })
    assert resp.status_code == 409


def test_create_product_requires_auth(client, mock_db):
    resp = client.post("/api/v1/products/", json={"name": "X", "sku": "S", "price": 1})
    assert resp.status_code == 401 or resp.status_code == 403


# ── GET /products/ ────────────────────────────────────────────────────────────


def test_list_products_returns_paginated(client, mock_db):
    mock_db.query.return_value = [PRODUCT]
    mock_db.count.return_value = 1

    resp = client.get("/api/v1/products/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["page"] == 1


def test_list_products_default_pagination(client, mock_db):
    mock_db.query.return_value = []
    mock_db.count.return_value = 0

    resp = client.get("/api/v1/products/")
    assert resp.status_code == 200


def test_list_products_with_filters(client, mock_db):
    mock_db.query.return_value = []
    mock_db.count.return_value = 0

    resp = client.get("/api/v1/products/?category_id=cat1&brand_id=brand1&status=active")
    assert resp.status_code == 200


# ── GET /products/{id} ────────────────────────────────────────────────────────


def test_get_product_found(client, mock_db):
    mock_db.select_one.return_value = PRODUCT

    resp = client.get("/api/v1/products/prod1")
    assert resp.status_code == 200
    assert resp.json()["sku"] == "SKU-001"


def test_get_product_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.get("/api/v1/products/missing")
    assert resp.status_code == 404


# ── PATCH /products/{id} ──────────────────────────────────────────────────────


def test_update_product_success(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "name": "Updated Widget"}

    resp = user_client.patch("/api/v1/products/prod1", json={"name": "Updated Widget"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Widget"


def test_update_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.patch("/api/v1/products/missing", json={"name": "X"})
    assert resp.status_code == 404


def test_update_product_locked_returns_423(user_client, mock_db):
    mock_db.select_one.return_value = {**PRODUCT, "locked": True}

    resp = user_client.patch("/api/v1/products/prod1", json={"name": "X"})
    assert resp.status_code == 423


# ── DELETE /products/{id} ─────────────────────────────────────────────────────


def test_delete_product_archives(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT

    resp = user_client.delete("/api/v1/products/prod1")
    assert resp.status_code == 204
    mock_db.update.assert_called()


def test_delete_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.delete("/api/v1/products/missing")
    assert resp.status_code == 404


# ── POST /products/{id}/restore ───────────────────────────────────────────────


def test_restore_product(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "status": "draft"}

    resp = user_client.post("/api/v1/products/prod1/restore")
    assert resp.status_code == 200


def test_restore_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/products/missing/restore")
    assert resp.status_code == 404


# ── POST /products/{id}/publish ───────────────────────────────────────────────


def test_publish_product(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "status": "active", "lifecycle_status": "active"}

    resp = user_client.post("/api/v1/products/prod1/publish")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_publish_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/products/missing/publish")
    assert resp.status_code == 404


# ── POST /products/{id}/unpublish ─────────────────────────────────────────────


def test_unpublish_product(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "status": "draft"}

    resp = user_client.post("/api/v1/products/prod1/unpublish")
    assert resp.status_code == 200


# ── POST /products/{id}/submit-for-review ─────────────────────────────────────


def test_submit_for_review(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "lifecycle_status": "pending_review"}

    resp = user_client.post("/api/v1/products/prod1/submit-for-review")
    assert resp.status_code == 200


# ── POST /products/{id}/approve ───────────────────────────────────────────────


def test_approve_product(admin_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "lifecycle_status": "approved"}

    resp = admin_client.post("/api/v1/products/prod1/approve")
    assert resp.status_code == 200
    assert resp.json()["lifecycle_status"] == "approved"


def test_approve_product_not_found(admin_client, mock_db):
    mock_db.select_one.return_value = None

    resp = admin_client.post("/api/v1/products/missing/approve")
    assert resp.status_code == 404


# ── POST /products/{id}/reject ────────────────────────────────────────────────


def test_reject_product(admin_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "lifecycle_status": "rejected"}

    resp = admin_client.post("/api/v1/products/prod1/reject", json={"reason": "Quality issues"})
    assert resp.status_code == 200


# ── POST /products/{id}/lock and unlock ───────────────────────────────────────


def test_lock_product(admin_client, mock_db):
    mock_db.update.return_value = {**PRODUCT, "locked": True}

    resp = admin_client.post("/api/v1/products/prod1/lock")
    assert resp.status_code == 200
    assert resp.json()["locked"] is True


def test_lock_product_not_found(admin_client, mock_db):
    mock_db.update.return_value = None

    resp = admin_client.post("/api/v1/products/missing/lock")
    assert resp.status_code == 404


def test_unlock_product(admin_client, mock_db):
    mock_db.update.return_value = {**PRODUCT, "locked": False}

    resp = admin_client.post("/api/v1/products/prod1/unlock")
    assert resp.status_code == 200
    assert resp.json()["locked"] is False


# ── GET /products/{id}/changelog ─────────────────────────────────────────────


def test_get_changelog(client, mock_db):
    mock_db.query.return_value = [{"action": "created", "created_at": "2024-01-01"}]

    resp = client.get("/api/v1/products/prod1/changelog")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── PATCH /products/{id}/seo ─────────────────────────────────────────────────


def test_update_seo(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "seo": {"title": "SEO Title"}}

    resp = user_client.patch("/api/v1/products/prod1/seo", json={"title": "SEO Title"})
    assert resp.status_code == 200


def test_update_seo_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.patch("/api/v1/products/missing/seo", json={"title": "X"})
    assert resp.status_code == 404


# ── GET /products/{id}/seo ────────────────────────────────────────────────────


def test_get_seo(client, mock_db):
    mock_db.select_one.return_value = {**PRODUCT, "seo": {"title": "Widget SEO"}}

    resp = client.get("/api/v1/products/prod1/seo")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Widget SEO"


def test_get_seo_product_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.get("/api/v1/products/missing/seo")
    assert resp.status_code == 404


def test_get_seo_no_seo_field_returns_empty(client, mock_db):
    mock_db.select_one.return_value = PRODUCT  # no "seo" key

    resp = client.get("/api/v1/products/prod1/seo")
    assert resp.status_code == 200
    assert resp.json() == {}


# ── PATCH /products/{id}/shipping ────────────────────────────────────────────


def test_update_shipping(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.update.return_value = {**PRODUCT, "shipping": {"weight": 1.5}}

    resp = user_client.patch("/api/v1/products/prod1/shipping", json={"weight": 1.5})
    assert resp.status_code == 200


# ── POST /products/{id}/shipping-rates ───────────────────────────────────────


DESTINATION = {"country": "US", "state": "NY", "zip": "10001"}


def test_get_shipping_rates_standard(client, mock_db):
    mock_db.select_one.return_value = {**PRODUCT, "shipping": {"weight": 1.0}}

    resp = client.post("/api/v1/products/prod1/shipping-rates", json={
        "destination": DESTINATION,
        "quantity": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rates"]) == 3
    carriers = [r["carrier"] for r in data["rates"]]
    assert "Standard" in carriers
    assert "Express" in carriers
    assert "Overnight" in carriers


def test_get_shipping_rates_increases_with_quantity(client, mock_db):
    mock_db.select_one.return_value = {**PRODUCT, "shipping": {"weight": 1.0}}

    resp1 = client.post("/api/v1/products/prod1/shipping-rates", json={"destination": DESTINATION, "quantity": 1})
    resp2 = client.post("/api/v1/products/prod1/shipping-rates", json={"destination": DESTINATION, "quantity": 3})

    rate1 = resp1.json()["rates"][0]["price"]
    rate2 = resp2.json()["rates"][0]["price"]
    assert rate2 > rate1


def test_get_shipping_rates_product_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.post("/api/v1/products/missing/shipping-rates", json={"destination": DESTINATION, "quantity": 1})
    assert resp.status_code == 404


# ── POST /products/{id}/duplicate ────────────────────────────────────────────


def test_duplicate_product(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.create.return_value = {**PRODUCT, "id": "prod2", "name": "Copy"}
    mock_db.query.return_value = []  # no variants/images/attrs

    resp = user_client.post("/api/v1/products/prod1/duplicate", json={"new_name": "Copy"})
    assert resp.status_code == 201


def test_duplicate_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/products/missing/duplicate", json={"new_name": "Copy"})
    assert resp.status_code == 404
