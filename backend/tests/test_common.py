"""Unit tests for models/common.py utility functions."""

import pytest
from app.models.common import Pagination, paginated, strip_none


# ── strip_none ────────────────────────────────────────────────────────────────


def test_strip_none_removes_none_values():
    result = strip_none({"a": 1, "b": None, "c": "hello", "d": None})
    assert result == {"a": 1, "c": "hello"}


def test_strip_none_empty_dict():
    assert strip_none({}) == {}


def test_strip_none_all_none():
    assert strip_none({"x": None, "y": None}) == {}


def test_strip_none_no_none():
    d = {"a": 1, "b": False, "c": 0, "d": ""}
    assert strip_none(d) == d  # False, 0, and "" are kept


def test_strip_none_does_not_mutate_original():
    original = {"a": 1, "b": None}
    strip_none(original)
    assert original == {"a": 1, "b": None}


# ── paginated ─────────────────────────────────────────────────────────────────


def test_paginated_first_page():
    result = paginated(["a", "b"], total=50, page=1, limit=20)
    assert result["items"] == ["a", "b"]
    assert result["total"] == 50
    assert result["page"] == 1
    assert result["limit"] == 20
    assert result["pages"] == 3  # ceil(50/20)


def test_paginated_exact_multiple():
    result = paginated([], total=40, page=2, limit=20)
    assert result["pages"] == 2


def test_paginated_single_page():
    result = paginated(["x"], total=1, page=1, limit=20)
    assert result["pages"] == 1


def test_paginated_zero_total():
    result = paginated([], total=0, page=1, limit=20)
    assert result["pages"] == 1  # at least 1 page even when empty


def test_paginated_ceiling_division():
    result = paginated([], total=21, page=1, limit=20)
    assert result["pages"] == 2


def test_paginated_large_dataset():
    result = paginated([], total=1000, page=5, limit=10)
    assert result["pages"] == 100
    assert result["page"] == 5


# ── Pagination model ──────────────────────────────────────────────────────────


def test_pagination_offset_page_one():
    p = Pagination(page=1, limit=20)
    assert p.offset == 0


def test_pagination_offset_page_three():
    p = Pagination(page=3, limit=10)
    assert p.offset == 20


def test_pagination_to_surql():
    p = Pagination(page=2, limit=5)
    assert p.to_surql() == "LIMIT 5 START 5"


def test_pagination_defaults():
    p = Pagination()
    assert p.page == 1
    assert p.limit == 20
    assert p.offset == 0
