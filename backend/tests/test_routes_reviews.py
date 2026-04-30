"""Unit tests for /reviews routes."""

import pytest

PRODUCT = {"id": "prod1", "name": "Widget"}
REVIEW = {
    "id": "rev1",
    "product_id": "prod1",
    "user_id": "user1",
    "rating": 4,
    "title": "Great product",
    "body": "Really liked it",
    "status": "approved",
    "helpful_count": 0,
}


# ── POST /products/{id}/reviews ───────────────────────────────────────────────


def test_submit_review_success(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.query.return_value = []  # no existing review
    mock_db.create.return_value = REVIEW

    resp = user_client.post("/api/v1/products/prod1/reviews", json={
        "rating": 4,
        "title": "Great product",
        "body": "Really liked it",
    })
    assert resp.status_code == 201
    assert resp.json()["rating"] == 4


def test_submit_review_product_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.post("/api/v1/products/missing/reviews", json={
        "rating": 3,
        "title": "OK",
        "body": "Fine",
    })
    assert resp.status_code == 404


def test_submit_review_duplicate_returns_409(user_client, mock_db):
    mock_db.select_one.return_value = PRODUCT
    mock_db.query.return_value = [{"id": "existing_review"}]  # already reviewed

    resp = user_client.post("/api/v1/products/prod1/reviews", json={
        "rating": 5,
        "title": "Again",
        "body": "Trying again",
    })
    assert resp.status_code == 409


def test_submit_review_requires_auth(client, mock_db):
    resp = client.post("/api/v1/products/prod1/reviews", json={
        "rating": 4,
        "title": "X",
        "body": "Y",
    })
    assert resp.status_code in (401, 403)


# ── GET /products/{id}/reviews ────────────────────────────────────────────────


def test_list_reviews(client, mock_db):
    mock_db.query.return_value = [REVIEW]
    mock_db.count.return_value = 1

    resp = client.get("/api/v1/products/prod1/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 1


def test_list_reviews_default_sort(client, mock_db):
    mock_db.query.return_value = []
    mock_db.count.return_value = 0

    resp = client.get("/api/v1/products/prod1/reviews?sort_by=newest")
    assert resp.status_code == 200


def test_list_reviews_sort_by_highest(client, mock_db):
    mock_db.query.return_value = []
    mock_db.count.return_value = 0

    resp = client.get("/api/v1/products/prod1/reviews?sort_by=highest")
    assert resp.status_code == 200


# ── PATCH /reviews/{review_id} ────────────────────────────────────────────────


def test_edit_review_success(user_client, mock_db):
    mock_db.select_one.return_value = REVIEW  # user_id matches REGULAR_USER["id"]
    mock_db.update.return_value = {**REVIEW, "title": "Updated"}

    resp = user_client.patch("/api/v1/reviews/rev1", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


def test_edit_review_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.patch("/api/v1/reviews/missing", json={"title": "X"})
    assert resp.status_code == 404


def test_edit_review_other_user_returns_403(user_client, mock_db):
    mock_db.select_one.return_value = {**REVIEW, "user_id": "other_user"}

    resp = user_client.patch("/api/v1/reviews/rev1", json={"title": "Sneaky"})
    assert resp.status_code == 403


# ── DELETE /reviews/{review_id} ───────────────────────────────────────────────


def test_delete_review_by_owner(user_client, mock_db):
    mock_db.select_one.return_value = REVIEW

    resp = user_client.delete("/api/v1/reviews/rev1")
    assert resp.status_code == 204
    mock_db.delete.assert_called_once_with("review", "rev1")


def test_delete_review_by_admin(admin_client, mock_db):
    other_review = {**REVIEW, "user_id": "someone_else"}
    mock_db.select_one.return_value = other_review

    resp = admin_client.delete("/api/v1/reviews/rev1")
    assert resp.status_code == 204


def test_delete_review_forbidden(user_client, mock_db):
    mock_db.select_one.return_value = {**REVIEW, "user_id": "other_user"}

    resp = user_client.delete("/api/v1/reviews/rev1")
    assert resp.status_code == 403


def test_delete_review_not_found(user_client, mock_db):
    mock_db.select_one.return_value = None

    resp = user_client.delete("/api/v1/reviews/missing")
    assert resp.status_code == 404


# ── POST /reviews/{review_id}/helpful ────────────────────────────────────────


def test_mark_helpful(client, mock_db):
    mock_db.select_one.return_value = {**REVIEW, "helpful_count": 5}

    resp = client.post("/api/v1/reviews/rev1/helpful")
    assert resp.status_code == 200
    assert resp.json()["helpful_count"] == 6


def test_mark_helpful_starts_at_zero(client, mock_db):
    mock_db.select_one.return_value = REVIEW  # helpful_count = 0

    resp = client.post("/api/v1/reviews/rev1/helpful")
    assert resp.status_code == 200
    assert resp.json()["helpful_count"] == 1


def test_mark_helpful_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.post("/api/v1/reviews/missing/helpful")
    assert resp.status_code == 404


# ── POST /reviews/{review_id}/report ─────────────────────────────────────────


def test_report_review(client, mock_db):
    mock_db.select_one.return_value = REVIEW
    mock_db.create.return_value = {"id": "report1"}

    resp = client.post("/api/v1/reviews/rev1/report", json={"reason": "spam"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Report submitted"


def test_report_review_not_found(client, mock_db):
    mock_db.select_one.return_value = None

    resp = client.post("/api/v1/reviews/missing/report", json={"reason": "spam"})
    assert resp.status_code == 404


# ── PATCH /reviews/{review_id}/moderate ──────────────────────────────────────


def test_moderate_review_approve(admin_client, mock_db):
    mock_db.select_one.return_value = {**REVIEW, "status": "pending"}
    mock_db.update.return_value = {**REVIEW, "status": "approved"}

    resp = admin_client.patch("/api/v1/reviews/rev1/moderate", json={"status": "approved"})
    assert resp.status_code == 200


def test_moderate_review_reject(admin_client, mock_db):
    mock_db.select_one.return_value = {**REVIEW, "status": "pending"}
    mock_db.update.return_value = {**REVIEW, "status": "rejected"}

    resp = admin_client.patch("/api/v1/reviews/rev1/moderate", json={"status": "rejected"})
    assert resp.status_code == 200


def test_moderate_review_not_found(admin_client, mock_db):
    mock_db.select_one.return_value = None

    resp = admin_client.patch("/api/v1/reviews/missing/moderate", json={"status": "approved"})
    assert resp.status_code == 404


def test_moderate_review_requires_admin(user_client, mock_db):
    resp = user_client.patch("/api/v1/reviews/rev1/moderate", json={"status": "approved"})
    assert resp.status_code == 403


# ── GET /products/{id}/rating-summary ────────────────────────────────────────


def test_rating_summary_with_reviews(client, mock_db):
    mock_db.query.return_value = [
        {"rating": 5, "cnt": 10},
        {"rating": 4, "cnt": 5},
        {"rating": 3, "cnt": 2},
    ]

    resp = client.get("/api/v1/products/prod1/rating-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 17
    assert data["average"] == round((5 * 10 + 4 * 5 + 3 * 2) / 17, 2)
    assert data["distribution"]["5"] == 10
    assert data["distribution"]["4"] == 5
    assert data["distribution"]["3"] == 2


def test_rating_summary_no_reviews(client, mock_db):
    mock_db.query.return_value = []

    resp = client.get("/api/v1/products/prod1/rating-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["average"] == 0.0


def test_rating_summary_all_five_stars(client, mock_db):
    mock_db.query.return_value = [{"rating": 5, "cnt": 3}]

    resp = client.get("/api/v1/products/prod1/rating-summary")
    assert resp.status_code == 200
    assert resp.json()["average"] == 5.0
