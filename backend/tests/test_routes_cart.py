"""Unit tests for /cart routes."""

import pytest

CART = {"id": "cart1", "user_id": "user1", "status": "active", "coupon_code": None}
PRODUCT = {"id": "prod1", "name": "Widget", "price": 10.0, "stock": 100}
CART_ITEM = {
    "id": "item1",
    "cart_id": "cart1",
    "product_id": "prod1",
    "variant_id": None,
    "quantity": 2,
    "unit_price": 10.0,
    "subtotal": 20.0,
}
COUPON = {"id": "coupon1", "code": "SAVE10", "type": "percentage", "value": 10, "is_active": True}


# ── POST /cart/ ───────────────────────────────────────────────────────────────


def test_create_cart(client, mock_db):
    mock_db.create.return_value = CART

    resp = client.post("/api/v1/cart/", json={"user_id": "user1"})
    assert resp.status_code == 201
    assert resp.json()["user_id"] == "user1"


# ── GET /cart/{cart_id} ───────────────────────────────────────────────────────


def test_get_cart_found(client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = [CART_ITEM]

    resp = client.get("/api/v1/cart/cart1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "cart1"
    assert len(data["items"]) == 1


def test_get_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.get("/api/v1/cart/missing")
    assert resp.status_code == 404


# ── POST /cart/{cart_id}/items ────────────────────────────────────────────────


def test_add_new_cart_item(client, mock_db):
    mock_db.select_one.side_effect = [CART, PRODUCT]  # cart then product
    mock_db.query.return_value = []  # no existing item
    mock_db.create.return_value = CART_ITEM

    resp = client.post("/api/v1/cart/cart1/items", json={
        "product_id": "prod1",
        "quantity": 2,
    })
    assert resp.status_code == 201
    assert resp.json()["product_id"] == "prod1"


def test_add_existing_cart_item_updates_quantity(client, mock_db):
    existing_item = {**CART_ITEM, "id": "cart_item:item1"}
    mock_db.select_one.side_effect = [CART, PRODUCT]
    mock_db.query.return_value = [existing_item]
    mock_db.update.return_value = {**CART_ITEM, "quantity": 4, "subtotal": 40.0}

    resp = client.post("/api/v1/cart/cart1/items", json={
        "product_id": "prod1",
        "quantity": 2,
    })
    assert resp.status_code == 201
    assert resp.json()["quantity"] == 4


def test_add_cart_item_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.post("/api/v1/cart/missing/items", json={"product_id": "p1", "quantity": 1})
    assert resp.status_code == 404


def test_add_cart_item_product_not_found(client, mock_db):
    mock_db.select_one.side_effect = [CART, None]  # cart found, product missing

    resp = client.post("/api/v1/cart/cart1/items", json={"product_id": "missing", "quantity": 1})
    assert resp.status_code == 404


def test_add_cart_item_uses_variant_price(client, mock_db):
    variant = {"id": "var1", "price": 15.0}
    mock_db.select_one.side_effect = [CART, PRODUCT, variant]
    mock_db.query.return_value = []
    mock_db.create.return_value = {**CART_ITEM, "unit_price": 15.0, "subtotal": 15.0}

    resp = client.post("/api/v1/cart/cart1/items", json={
        "product_id": "prod1",
        "variant_id": "var1",
        "quantity": 1,
    })
    assert resp.status_code == 201


# ── PATCH /cart/{cart_id}/items/{item_id} ────────────────────────────────────


def test_update_cart_item_quantity(client, mock_db):
    mock_db.select_one.return_value = CART_ITEM
    mock_db.update.return_value = {**CART_ITEM, "quantity": 5, "subtotal": 50.0}

    resp = client.patch("/api/v1/cart/cart1/items/item1", json={"quantity": 5})
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 5


def test_update_cart_item_quantity_zero_removes_item(client, mock_db):
    mock_db.select_one.return_value = CART_ITEM

    resp = client.patch("/api/v1/cart/cart1/items/item1", json={"quantity": 0})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Item removed"
    mock_db.delete.assert_called_once_with("cart_item", "item1")


def test_update_cart_item_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.patch("/api/v1/cart/cart1/items/missing", json={"quantity": 1})
    assert resp.status_code == 404


def test_update_cart_item_wrong_cart(client, mock_db):
    mock_db.select_one.return_value = {**CART_ITEM, "cart_id": "other_cart"}

    resp = client.patch("/api/v1/cart/cart1/items/item1", json={"quantity": 1})
    assert resp.status_code == 404


# ── DELETE /cart/{cart_id}/items/{item_id} ───────────────────────────────────


def test_remove_cart_item(client, mock_db):
    mock_db.select_one.return_value = CART_ITEM

    resp = client.delete("/api/v1/cart/cart1/items/item1")
    assert resp.status_code == 204
    mock_db.delete.assert_called_once_with("cart_item", "item1")


def test_remove_cart_item_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.delete("/api/v1/cart/cart1/items/missing")
    assert resp.status_code == 404


# ── DELETE /cart/{cart_id}/clear ─────────────────────────────────────────────


def test_clear_cart(client, mock_db):
    mock_db.select_one.return_value = CART

    resp = client.delete("/api/v1/cart/cart1/clear")
    assert resp.status_code == 204
    mock_db.query.assert_called()


def test_clear_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.delete("/api/v1/cart/missing/clear")
    assert resp.status_code == 404


# ── POST /cart/{cart_id}/coupon ───────────────────────────────────────────────


def test_apply_coupon_success(client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = [COUPON]

    resp = client.post("/api/v1/cart/cart1/coupon", json={"code": "SAVE10"})
    assert resp.status_code == 200
    assert resp.json()["coupon_code"] == "SAVE10"


def test_apply_coupon_invalid(client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = []  # no matching coupon

    resp = client.post("/api/v1/cart/cart1/coupon", json={"code": "INVALID"})
    assert resp.status_code == 422


def test_apply_coupon_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.post("/api/v1/cart/missing/coupon", json={"code": "SAVE10"})
    assert resp.status_code == 404


# ── DELETE /cart/{cart_id}/coupon ─────────────────────────────────────────────


def test_remove_coupon(client, mock_db):
    mock_db.select_one.return_value = {**CART, "coupon_code": "SAVE10"}

    resp = client.delete("/api/v1/cart/cart1/coupon")
    assert resp.status_code == 204
    mock_db.update.assert_called()


def test_remove_coupon_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.delete("/api/v1/cart/missing/coupon")
    assert resp.status_code == 404


# ── POST /cart/merge ──────────────────────────────────────────────────────────


def test_merge_carts_success(client, mock_db):
    guest_cart = {"id": "guest1", "status": "active"}
    user_cart = {"id": "user_cart1", "status": "active"}
    mock_db.select_one.side_effect = [guest_cart, user_cart]
    mock_db.query.side_effect = [
        [CART_ITEM],  # guest items
        [],           # no matching item in user cart
        [CART_ITEM],  # final merged items
    ]

    resp = client.post("/api/v1/cart/merge", json={
        "guest_cart_id": "guest1",
        "user_cart_id": "user_cart1",
    })
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_merge_carts_guest_not_found(client, mock_db):
    mock_db.select_one.side_effect = [None, {"id": "user_cart1"}]

    resp = client.post("/api/v1/cart/merge", json={
        "guest_cart_id": "missing",
        "user_cart_id": "user_cart1",
    })
    assert resp.status_code == 404


def test_merge_carts_user_cart_not_found(client, mock_db):
    mock_db.select_one.side_effect = [{"id": "guest1"}, None]

    resp = client.post("/api/v1/cart/merge", json={
        "guest_cart_id": "guest1",
        "user_cart_id": "missing",
    })
    assert resp.status_code == 404


# ── GET /cart/{cart_id}/summary ───────────────────────────────────────────────


def test_cart_summary_no_coupon(client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = [{"total": 60.0}]

    resp = client.get("/api/v1/cart/cart1/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["subtotal"] == 60.0
    assert data["discount"] == 0.0
    assert data["shipping_estimate"] == 0.0  # free over $50
    assert data["tax"] == round(60.0 * 0.08, 2)


def test_cart_summary_below_free_shipping_threshold(client, mock_db):
    mock_db.select_one.return_value = CART
    mock_db.query.return_value = [{"total": 30.0}]

    resp = client.get("/api/v1/cart/cart1/summary")
    assert resp.status_code == 200
    assert resp.json()["shipping_estimate"] == 5.99


def test_cart_summary_percentage_coupon(client, mock_db):
    cart_with_coupon = {**CART, "coupon_code": "SAVE10"}
    mock_db.select_one.return_value = cart_with_coupon
    mock_db.query.side_effect = [
        [{"total": 100.0}],  # subtotal query
        [{**COUPON, "type": "percentage", "value": 10}],  # coupon query
    ]

    resp = client.get("/api/v1/cart/cart1/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["discount"] == 10.0


def test_cart_summary_fixed_coupon(client, mock_db):
    cart_with_coupon = {**CART, "coupon_code": "FIXED5"}
    fixed_coupon = {**COUPON, "code": "FIXED5", "type": "fixed", "value": 5.0}
    mock_db.select_one.return_value = cart_with_coupon
    mock_db.query.side_effect = [
        [{"total": 50.0}],
        [fixed_coupon],
    ]

    resp = client.get("/api/v1/cart/cart1/summary")
    assert resp.status_code == 200
    assert resp.json()["discount"] == 5.0


def test_cart_summary_free_shipping_coupon(client, mock_db):
    cart_with_coupon = {**CART, "coupon_code": "FREESHIP"}
    free_ship_coupon = {**COUPON, "code": "FREESHIP", "type": "free_shipping", "value": 0}
    mock_db.select_one.return_value = cart_with_coupon
    mock_db.query.side_effect = [
        [{"total": 20.0}],  # below threshold, but coupon gives free shipping
        [free_ship_coupon],
    ]

    resp = client.get("/api/v1/cart/cart1/summary")
    assert resp.status_code == 200
    assert resp.json()["shipping_estimate"] == 0.0


def test_cart_summary_cart_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.get("/api/v1/cart/missing/summary")
    assert resp.status_code == 404
