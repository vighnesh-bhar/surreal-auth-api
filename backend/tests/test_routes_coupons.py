"""Unit tests for /coupons routes."""

import pytest

COUPON = {
    "id": "coupon1",
    "code": "SAVE10",
    "type": "percentage",
    "value": 10,
    "is_active": True,
    "usage_count": 0,
    "usage_limit": None,
    "min_order_value": 0,
    "starts_at": None,
    "ends_at": None,
}

CART = {"id": "cart1", "user_id": "user1", "status": "active"}


# ── POST /coupons/ ────────────────────────────────────────────────────────────


def test_create_coupon_success(admin_client, mock_db):
    mock_db.query.return_value = []  # no duplicate
    mock_db.create.return_value = COUPON

    resp = admin_client.post("/api/v1/coupons/", json={
        "code": "SAVE10",
        "type": "percentage",
        "value": 10,
    })
    assert resp.status_code == 201
    assert resp.json()["code"] == "SAVE10"


def test_create_coupon_duplicate_code_returns_409(admin_client, mock_db):
    mock_db.query.return_value = [{"id": "existing"}]

    resp = admin_client.post("/api/v1/coupons/", json={
        "code": "SAVE10",
        "type": "percentage",
        "value": 10,
    })
    assert resp.status_code == 409


def test_create_coupon_requires_admin(user_client, mock_db):
    resp = user_client.post("/api/v1/coupons/", json={
        "code": "SAVE10",
        "type": "percentage",
        "value": 10,
    })
    assert resp.status_code == 403


# ── GET /coupons/ ─────────────────────────────────────────────────────────────


def test_list_coupons(admin_client, mock_db):
    mock_db.query.return_value = [COUPON]

    resp = admin_client.get("/api/v1/coupons/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["code"] == "SAVE10"


def test_list_coupons_requires_admin(client, mock_db):
    resp = client.get("/api/v1/coupons/")
    assert resp.status_code in (401, 403)


# ── POST /coupons/validate ────────────────────────────────────────────────────


def test_validate_coupon_success(client, mock_db):
    mock_db.query.side_effect = [
        [COUPON],           # coupon lookup
        [{"total": 50.0}],  # cart total
    ]
    mock_db.select_one.return_value = CART

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["discount"] == 5.0  # 10% of 50


def test_validate_coupon_invalid_code_returns_422(client, mock_db):
    mock_db.query.return_value = []  # no coupon found

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "FAKE",
        "cart_id": "cart1",
    })
    assert resp.status_code == 422


def test_validate_coupon_not_yet_active(client, mock_db):
    future_coupon = {**COUPON, "starts_at": "2099-01-01T00:00:00+00:00"}
    mock_db.query.return_value = [future_coupon]

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 422


def test_validate_coupon_expired(client, mock_db):
    expired_coupon = {**COUPON, "ends_at": "2000-01-01T00:00:00+00:00"}
    mock_db.query.return_value = [expired_coupon]

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 422


def test_validate_coupon_usage_limit_reached(client, mock_db):
    maxed_coupon = {**COUPON, "usage_limit": 5, "usage_count": 5}
    mock_db.query.return_value = [maxed_coupon]

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 422


def test_validate_coupon_cart_not_found(client, mock_db):
    mock_db.query.return_value = [COUPON]
    mock_db.select_one.return_value = None  # cart missing

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "missing",
    })
    assert resp.status_code == 404


def test_validate_coupon_min_order_not_met(client, mock_db):
    coupon_with_min = {**COUPON, "min_order_value": 100.0}
    mock_db.query.side_effect = [
        [coupon_with_min],
        [{"total": 30.0}],  # below minimum
    ]
    mock_db.select_one.return_value = CART

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 422


def test_validate_coupon_fixed_type(client, mock_db):
    fixed_coupon = {**COUPON, "type": "fixed", "value": 8.0}
    mock_db.query.side_effect = [
        [fixed_coupon],
        [{"total": 50.0}],
    ]
    mock_db.select_one.return_value = CART

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "SAVE10",
        "cart_id": "cart1",
    })
    assert resp.status_code == 200
    assert resp.json()["discount"] == 8.0


def test_validate_coupon_free_shipping_type(client, mock_db):
    fs_coupon = {**COUPON, "type": "free_shipping", "value": 0}
    mock_db.query.side_effect = [
        [fs_coupon],
        [{"total": 25.0}],
    ]
    mock_db.select_one.return_value = CART

    resp = client.post("/api/v1/coupons/validate", json={
        "code": "FREESHIP",
        "cart_id": "cart1",
    })
    assert resp.status_code == 200
    assert resp.json()["discount"] == 0  # handled at checkout


# ── DELETE /coupons/{coupon_id} ───────────────────────────────────────────────


def test_delete_coupon_success(admin_client, mock_db):
    mock_db.update.return_value = {**COUPON, "is_active": False}

    resp = admin_client.delete("/api/v1/coupons/coupon1")
    assert resp.status_code == 204


def test_delete_coupon_not_found(admin_client, mock_db):
    mock_db.update.return_value = None

    resp = admin_client.delete("/api/v1/coupons/missing")
    assert resp.status_code == 404


def test_delete_coupon_requires_admin(user_client, mock_db):
    resp = user_client.delete("/api/v1/coupons/coupon1")
    assert resp.status_code == 403
