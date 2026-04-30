"""Unit tests for database.py pure helper functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.db.surreal import DB, _extract_id, _unwrap, normalise, surreal_id


# ── _extract_id ───────────────────────────────────────────────────────────────


def test_extract_id_from_colon_string():
    assert _extract_id("product:abc123") == "abc123"


def test_extract_id_plain_string():
    assert _extract_id("abc123") == "abc123"


def test_extract_id_none():
    assert _extract_id(None) == ""


def test_extract_id_record_id_object():
    mock_rid = MagicMock()
    mock_rid.id = "xyz789"
    assert _extract_id(mock_rid) == "xyz789"


def test_extract_id_record_id_object_takes_priority_over_colon():
    mock_rid = MagicMock()
    mock_rid.id = "plain"
    assert _extract_id(mock_rid) == "plain"


# ── normalise ─────────────────────────────────────────────────────────────────


def test_normalise_extracts_id():
    record = {"id": "product:abc", "name": "Widget"}
    result = normalise(record)
    assert result["id"] == "abc"
    assert result["name"] == "Widget"


def test_normalise_none_returns_empty_dict():
    assert normalise(None) == {}


def test_normalise_empty_dict_returns_empty():
    assert normalise({}) == {}


def test_normalise_no_id_field():
    record = {"name": "No ID"}
    result = normalise(record)
    assert result == {"name": "No ID"}


def test_normalise_does_not_mutate_original():
    record = {"id": "table:1", "val": 10}
    normalise(record)
    assert record["id"] == "table:1"  # original unchanged


# ── _unwrap ───────────────────────────────────────────────────────────────────


def test_unwrap_new_sdk_flat_list():
    records = [{"id": "a"}, {"id": "b"}]
    assert _unwrap(records) == records


def test_unwrap_old_sdk_wrapper():
    wrapped = [{"result": [{"id": "x"}], "status": "OK"}]
    assert _unwrap(wrapped) == [{"id": "x"}]


def test_unwrap_none():
    assert _unwrap(None) == []


def test_unwrap_single_dict():
    assert _unwrap({"id": "one"}) == [{"id": "one"}]


def test_unwrap_empty_list():
    assert _unwrap([]) == []


def test_unwrap_old_sdk_empty_result():
    wrapped = [{"result": [], "status": "OK"}]
    assert _unwrap(wrapped) == []


# ── surreal_id ────────────────────────────────────────────────────────────────


def test_surreal_id_format():
    assert surreal_id("product", "abc123") == "product:abc123"


def test_surreal_id_user_table():
    assert surreal_id("user", "admin1") == "user:admin1"


# ── DB.count ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_count_with_where():
    mock_client = MagicMock()
    mock_client.query = AsyncMock(return_value=[{"n": 5}])
    db = DB(mock_client)
    db.query = AsyncMock(return_value=[{"n": 5}])
    result = await db.count("product", "status = 'active'")
    assert result == 5


@pytest.mark.asyncio
async def test_db_count_empty_result():
    mock_client = MagicMock()
    db = DB(mock_client)
    db.query = AsyncMock(return_value=[])
    result = await db.count("product")
    assert result == 0


# ── DB.exists ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_exists_found():
    mock_client = MagicMock()
    db = DB(mock_client)
    db.select_one = AsyncMock(return_value={"id": "1"})
    assert await db.exists("product", "1") is True


@pytest.mark.asyncio
async def test_db_exists_not_found():
    mock_client = MagicMock()
    db = DB(mock_client)
    db.select_one = AsyncMock(return_value=None)
    assert await db.exists("product", "missing") is False
