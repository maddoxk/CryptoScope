"""SQLite database layer — caching, watchlists, and historical snapshots."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

from cryptoscope.config import CONFIG_DIR

logger = logging.getLogger(__name__)

DB_PATH = CONFIG_DIR / "cryptoscope.db"

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key   TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    ttl_seconds INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS watchlist (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL DEFAULT 'default',
    coin_id  TEXT NOT NULL,
    added_at REAL NOT NULL,
    UNIQUE(name, coin_id)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    coin_id    TEXT NOT NULL,
    price_usd  REAL NOT NULL,
    market_cap REAL,
    volume_24h REAL,
    change_24h REAL,
    timestamp  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_key ON api_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_coin ON price_snapshots(coin_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_watchlist_name ON watchlist(name);
"""


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()
        logger.info("Database initialized at %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # --- API Cache ---

    async def cache_get(self, key: str) -> Any | None:
        """Get a cached value if it exists and hasn't expired."""
        async with self.db.execute(
            "SELECT data, created_at, ttl_seconds FROM api_cache WHERE cache_key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            created_at = row["created_at"]
            ttl = row["ttl_seconds"]
            if time.time() - created_at > ttl:
                await self.db.execute("DELETE FROM api_cache WHERE cache_key = ?", (key,))
                await self.db.commit()
                return None
            return json.loads(row["data"])

    async def cache_set(self, key: str, data: Any, ttl_seconds: int = 60) -> None:
        """Store a value in the cache."""
        await self.db.execute(
            """INSERT OR REPLACE INTO api_cache (cache_key, data, created_at, ttl_seconds)
               VALUES (?, ?, ?, ?)""",
            (key, json.dumps(data), time.time(), ttl_seconds),
        )
        await self.db.commit()

    async def cache_clear_expired(self) -> int:
        """Remove all expired cache entries. Returns count removed."""
        now = time.time()
        cursor = await self.db.execute(
            "DELETE FROM api_cache WHERE (? - created_at) > ttl_seconds",
            (now,),
        )
        await self.db.commit()
        return cursor.rowcount

    # --- Watchlist ---

    async def watchlist_get(self, name: str = "default") -> list[str]:
        """Get coin IDs in a watchlist."""
        async with self.db.execute(
            "SELECT coin_id FROM watchlist WHERE name = ? ORDER BY added_at",
            (name,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row["coin_id"] for row in rows]

    async def watchlist_add(self, coin_id: str, name: str = "default") -> None:
        """Add a coin to a watchlist."""
        await self.db.execute(
            "INSERT OR IGNORE INTO watchlist (name, coin_id, added_at) VALUES (?, ?, ?)",
            (name, coin_id, time.time()),
        )
        await self.db.commit()

    async def watchlist_remove(self, coin_id: str, name: str = "default") -> None:
        """Remove a coin from a watchlist."""
        await self.db.execute(
            "DELETE FROM watchlist WHERE name = ? AND coin_id = ?",
            (name, coin_id),
        )
        await self.db.commit()

    async def watchlist_list_names(self) -> list[str]:
        """Get all watchlist names."""
        async with self.db.execute(
            "SELECT DISTINCT name FROM watchlist ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row["name"] for row in rows]

    # --- Price Snapshots ---

    async def snapshot_save(
        self,
        coin_id: str,
        price_usd: float,
        market_cap: float = 0,
        volume_24h: float = 0,
        change_24h: float = 0,
    ) -> None:
        """Save a price snapshot."""
        await self.db.execute(
            """INSERT INTO price_snapshots
               (coin_id, price_usd, market_cap, volume_24h, change_24h, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (coin_id, price_usd, market_cap, volume_24h, change_24h, time.time()),
        )
        await self.db.commit()

    async def snapshot_get_history(
        self,
        coin_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent price snapshots for a coin."""
        async with self.db.execute(
            """SELECT price_usd, market_cap, volume_24h, change_24h, timestamp
               FROM price_snapshots
               WHERE coin_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (coin_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def snapshot_get_recent_prices(
        self, coin_id: str, limit: int = 20
    ) -> list[float]:
        """Get recent price values for sparkline rendering."""
        async with self.db.execute(
            """SELECT price_usd FROM price_snapshots
               WHERE coin_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (coin_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            # Reverse so oldest is first (left of sparkline)
            return [row["price_usd"] for row in reversed(rows)]

    async def snapshot_cleanup(self, max_age_days: int = 30) -> int:
        """Remove snapshots older than max_age_days. Returns count removed."""
        cutoff = time.time() - (max_age_days * 86400)
        cursor = await self.db.execute(
            "DELETE FROM price_snapshots WHERE timestamp < ?",
            (cutoff,),
        )
        await self.db.commit()
        return cursor.rowcount
