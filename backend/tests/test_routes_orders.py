"""Unit tests for /orders routes."""

import pytest

ORDER = {
    "id": "order1",
    "user_id": "user1",
    "cart_id": "cart1",
    "status": "pending",
    "subtotal": 50.0,
    "discount": 0.0,
    "tax": 4.0,
    "shipping_cost": 0.0,
    "grand_total": 54.0,
}

CART = {"id": "cart1", "user_id": "user1", "status": "active", "coupon_code": None}

CART_ITEM = {
    "id": "item1",
    "cart_id": "cart1",
    "product_id": "prod1",
    "variant_id": None,
    "quantity": 2,
    "unit_price": 25.0,
    "subtotal": 50.0,
}

PRODUCT = {"id": "prod1", "name": "Widget", "price": 25.0, "stock": 100, "reserved": 0}

ORDER_ITEM = {
    "id": "oi1",
    "order_id": "order1",
    "product_id": "prod1",
    "quantity": 2,
    "unit_price": 25.0,
    "subtotal": 50.0,
    "refunded_qty": 0,
}


# ── POST /orders/ ─────────────────────────────────────────────────────────────


def test_place_order_success(user_client, mock_db):
    mock_db.select_one.side_effect = [
        CART,       # cart lookup
        PRODUCT,    # stock check for item
        PRODUCT,    # product name for order_item
        PRODUCT,    # stock deduction
    ]
    mock_db.query.return_value = [CART_ITEM]  # cart items
    mock_db.create.return_value = ORDER

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "cart1",
        "shipping_address": {"line1": "123 Main St", "city": "NYC"},
        "billing_address": {"line1": "123 Main St", "city": "NYC"},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 201


def test_place_order_cart_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "missing",
        "shipping_address": {},
        "billing_address": {},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 404


def test_place_order_already_used_cart_returns_409(user_client, mock_db):
    mock_db.select_one.return_value = {**CART, "status": "completed"}

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "cart1",
        "shipping_address": {},
        "billing_address": {},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 409


def test_place_order_empty_cart_returns_422(user_client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = []  # no cart items

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "cart1",
        "shipping_address": {},
        "billing_address": {},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 422


def test_place_order_insufficient_stock_returns_422(user_client, mock_db):
    low_stock_product = {**PRODUCT, "stock": 1, "reserved": 0}
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = [{**CART_ITEM, "quantity": 5}]  # wants 5
    # second select_one call returns the product with only 1 stock
    from unittest.mock import AsyncMock
    mock_db.select_one = AsyncMock(side_effect=[CART, low_stock_product])

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "cart1",
        "shipping_address": {},
        "billing_address": {},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 422


def test_place_order_with_percentage_coupon(user_client, mock_db):
    coupon = {"id": "c1", "type": "percentage", "value": 10, "is_active": True}
    cart_with_coupon = {**CART, "coupon_code": "SAVE10"}
    mock_db.select_one.side_effect = [cart_with_coupon, PRODUCT, PRODUCT, PRODUCT]
    mock_db.query.side_effect = [
        [CART_ITEM],      # cart items
        [coupon],         # coupon lookup
        [ORDER_ITEM],     # order items after creation
    ]
    mock_db.create.return_value = {**ORDER, "coupon_code": "SAVE10"}

    resp = user_client.post("/api/v1/orders/", json={
        "cart_id": "cart1",
        "shipping_address": {},
        "billing_address": {},
        "payment_method_id": "pm_1",
    })
    assert resp.status_code == 201


# ── GET /orders/ ──────────────────────────────────────────────────────────────


def test_list_orders(user_client, mock_db):
    mock_db.query.return_value = [ORDER]

    resp = user_client.get("/api/v1/orders/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["id"] == "order1"


def test_list_orders_empty(user_client, mock_db):
    mock_db.query.return_value = []

    resp = user_client.get("/api/v1/orders/")
    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /orders/{order_id} ────────────────────────────────────────────────────


def test_get_order_found(user_client, mock_db):
    mock_db.select_one.return_value = ORDER
    mock_db.query.return_value = [ORDER_ITEM]

    resp = user_client.get("/api/v1/orders/order1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "order1"
    assert "items" in resp.json()


def test_get_order_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.get("/api/v1/orders/missing")
    assert resp.status_code == 404


def test_get_order_forbidden_for_other_user(user_client, mock_db):
    other_order = {**ORDER, "user_id": "other_user"}
    mock_db.select_one.return_value = other_order

    resp = user_client.get("/api/v1/orders/order1")
    assert resp.status_code == 403


# ── PATCH /orders/{order_id}/cancel ──────────────────────────────────────────


def test_cancel_order_success(user_client, mock_db):
    mock_db.select_one.return_value = {**ORDER, "status": "pending"}
    mock_db.update.return_value = {**ORDER, "status": "cancelled"}
    mock_db.query.return_value = []  # no reservations

    resp = user_client.patch("/api/v1/orders/order1/cancel", json={"reason": "Changed my mind"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_order_invalid_status_returns_409(user_client, mock_db):
    mock_db.select_one.return_value = {**ORDER, "status": "delivered"}

    resp = user_client.patch("/api/v1/orders/order1/cancel", json={"reason": "Too late"})
    assert resp.status_code == 409


def test_cancel_order_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.patch("/api/v1/orders/missing/cancel", json={"reason": "X"})
    assert resp.status_code == 404


def test_cancel_order_forbidden_other_user(user_client, mock_db):
    mock_db.select_one.return_value = {**ORDER, "user_id": "other"}

    resp = user_client.patch("/api/v1/orders/order1/cancel", json={"reason": "X"})
    assert resp.status_code == 403


# ── POST /orders/{order_id}/refund ────────────────────────────────────────────


def test_refund_order_success(user_client, mock_db):
    delivered_order = {**ORDER, "status": "delivered"}
    order_item = {**ORDER_ITEM, "refunded_qty": 0}

    from unittest.mock import AsyncMock
    mock_db.select_one = AsyncMock(side_effect=[delivered_order, order_item, PRODUCT])
    mock_db.query.return_value = [order_item]  # for full refund check
    mock_db.create.return_value = {"id": "refund1", "total": 25.0}

    resp = user_client.post("/api/v1/orders/order1/refund", json={
        "items": [{"order_item_id": "oi1", "quantity": 1}],
        "reason": "Defective",
        "refund_method": "original",
    })
    assert resp.status_code == 200


def test_refund_order_invalid_status_returns_409(user_client, mock_db):
    mock_db.select_one.return_value = {**ORDER, "status": "pending"}

    resp = user_client.post("/api/v1/orders/order1/refund", json={
        "items": [{"order_item_id": "oi1", "quantity": 1}],
        "reason": "X",
        "refund_method": "original",
    })
    assert resp.status_code == 409


# ── GET /orders/{order_id}/tracking ──────────────────────────────────────────


def test_order_tracking(client, mock_db):
    order_with_tracking = {
        **ORDER,
        "tracking_number": "TRACK123",
        "carrier": "FedEx",
    }
    mock_db.select_one.return_value = order_with_tracking

    resp = client.get("/api/v1/orders/order1/tracking")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tracking_number"] == "TRACK123"
    assert data["carrier"] == "FedEx"
    assert data["status"] == "pending"


def test_order_tracking_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.get("/api/v1/orders/missing/tracking")
    assert resp.status_code == 404


# ── PATCH /orders/{order_id}/status ──────────────────────────────────────────


def test_update_order_status(admin_client, mock_db):
    mock_db.select_one.return_value = ORDER
    mock_db.update.return_value = {**ORDER, "status": "shipped", "tracking_number": "TN123"}

    resp = admin_client.patch("/api/v1/orders/order1/status", json={
        "status": "shipped",
        "tracking_number": "TN123",
        "carrier": "UPS",
    })
    assert resp.status_code == 200


def test_update_order_status_not_found(admin_client, mock_db):
    mock_db.select_one.return_value = None

    resp = admin_client.patch("/api/v1/orders/missing/status", json={"status": "shipped"})
    assert resp.status_code == 404


# ── POST /orders/{order_id}/invoice ──────────────────────────────────────────


def test_generate_invoice(user_client, mock_db):
    mock_db.select_one.return_value = ORDER
    mock_db.query.return_value = [ORDER_ITEM]

    resp = user_client.post("/api/v1/orders/order1/invoice")
    assert resp.status_code == 200
    data = resp.json()
    assert "invoice_number" in data
    assert data["invoice_number"].startswith("INV-")
    assert "items" in data


def test_generate_invoice_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/orders/missing/invoice")
    assert resp.status_code == 404


def test_generate_invoice_forbidden_other_user(user_client, mock_db):
    mock_db.select_one.return_value = {**ORDER, "user_id": "other"}

    resp = user_client.post("/api/v1/orders/order1/invoice")
    assert resp.status_code == 403
