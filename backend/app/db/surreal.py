
from __future__ import annotations

import logging
from typing import Any, Optional

from surrealdb import AsyncSurreal

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Singleton ──────────────────────────────────────────────────────────────────

_client: Optional[AsyncSurreal] = None


async def connect_db() -> None:
    """Called once at app startup (FastAPI lifespan)."""
    global _client
    url = settings.SURREAL_URL  
    _client = AsyncSurreal(url)
    await _client.connect(url)
    await _client.signin({"username": settings.SURREAL_USERNAME, "password": settings.SURREAL_PASSWORD})
    await _client.use(settings.SURREAL_NAMESPACE, settings.SURREAL_DB)
    logger.info(
        "Connected to SurrealDB at %s [ns=%s db=%s]",
        url,
        settings.SURREAL_NAMESPACE,
        settings.SURREAL_DB,
    )


async def disconnect_db() -> None:
    """Called once at app shutdown (FastAPI lifespan)."""
    global _client
    if _client:
        await _client.close()
        _client = None
        logger.info("🔌  SurrealDB connection closed.")


def get_client() -> AsyncSurreal:
    if _client is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _client


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_id(raw_id: Any) -> str:
    """Normalise a RecordID object or 'table:id' string → plain id string."""
    if raw_id is None:
        return ""
    # New SDK: RecordID object
    if hasattr(raw_id, "id"):
        return str(raw_id.id)
    # Old SDK / raw string: "table:id"
    s = str(raw_id)
    return s.split(":", 1)[1] if ":" in s else s



def normalise(record: Any) -> dict:
    """
    Convert a SurrealDB record dict to a clean Python dict with a plain string `id`.
    Returns {} if record is None/falsy.
    """
    if not record:
        return {}
    record = dict(record)
    if "id" in record:
        record["id"] = _extract_id(record["id"])
    return record


def _unwrap(raw: Any) -> list[dict]:
    """
    The new SDK returns query results directly as a list (not wrapped in
    {result: [...], status: 'OK'}).  Handle both old and new shapes.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        # New SDK: list of records, or list of result-dicts (old SDK)
        if raw and isinstance(raw[0], dict) and "result" in raw[0] and "status" in raw[0]:
            # Old SDK wrapper shape
            return raw[0].get("result") or []
        return raw
    if isinstance(raw, dict):
        # Single record returned directly
        return [raw]
    return []


def surreal_id(table: str, record_id: str) -> str:
    """Build a fully-qualified SurrealDB record ID: 'product:abc123'."""
    return f"{table}:{record_id}"


# ── FastAPI dependency ────────────────────────────────────────────────────────

class DB:
    """
    Thin wrapper around the AsyncSurreal client that exposes clean helper
    methods and normalises record IDs across SDK versions.
    """

    def __init__(self, client: AsyncSurreal):
        self._db = client

    # ── Low-level ────────────────────────────────────────────────────────────

    async def query(self, sql: str, vars: Optional[dict] = None) -> list[Any]:
        """Execute a raw SurrealQL statement. Returns a list of records."""
        raw = await self._db.query(sql, vars or {})
        rows = _unwrap(raw)
        return [normalise(r) if isinstance(r, dict) else r for r in rows]

    async def query_all(self, sql: str, vars: Optional[dict] = None) -> list[list[Any]]:
        """Execute multi-statement SurrealQL; returns results for every statement."""
        raw = await self._db.query(sql, vars or {})
        if isinstance(raw, list):
            # New SDK: single flat list — wrap as single result set
            if raw and isinstance(raw[0], dict) and "result" in raw[0]:
                return [raw[0].get("result") or []]
            return [raw]
        return []

    # ── CRUD helpers ─────────────────────────────────────────────────────────

    async def create(self, table: str, data: dict) -> dict:
        """INSERT one record; returns the created record with normalised id."""
        record = await self._db.create(table, data)
        if isinstance(record, list):
            record = record[0] if record else {}
        return normalise(record)

    async def select_one(self, table: str, record_id: str) -> Optional[dict]:
        """SELECT a single record by id string (without table prefix)."""
        try:
            record = await self._db.select(f"{table}:{record_id}")
            if isinstance(record, list):
                record = record[0] if record else None
            return normalise(record) if record else None
        except Exception:
            return None

    async def select_all(self, table: str) -> list[dict]:
        """SELECT * FROM <table>."""
        records = await self._db.select(table)
        if isinstance(records, list):
            return [normalise(r) for r in records]
        return []

    async def update(self, table: str, record_id: str, data: dict) -> Optional[dict]:
        """MERGE (partial update) a record."""
        record = await self._db.merge(f"{table}:{record_id}", data)
        if isinstance(record, list):
            record = record[0] if record else None
        return normalise(record) if record else None

    async def delete(self, table: str, record_id: str) -> bool:
        """DELETE a record; returns True on success."""
        try:
            await self._db.delete(f"{table}:{record_id}")
            return True
        except Exception:
            return False

    # ── Convenience ──────────────────────────────────────────────────────────

    async def exists(self, table: str, record_id: str) -> bool:
        return (await self.select_one(table, record_id)) is not None

    async def count(self, table: str, where: str = "") -> int:
        clause = f"WHERE {where}" if where else ""
        rows = await self.query(f"SELECT count() AS n FROM {table} {clause} GROUP ALL")
        return rows[0]["n"] if rows else 0


async def get_db() -> DB:
    """FastAPI dependency — inject with `db: DB = Depends(get_db)`."""
    return DB(get_client())
