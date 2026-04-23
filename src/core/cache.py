"""SQLite-backed cache for API and BigWig responses."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from src.core.exceptions import CacheError

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""

_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at);"


class Cache:
    """Thread-safe SQLite cache with TTL expiry.

    Key format: ``"{source}:{chrom}:{start}:{end}"``

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path = "data/cache/orcsonar_cache.db") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()
        logger.debug(f"Cache initialised at {self._path}")

    # ------------------------------------------------------------------
    def get(self, key: str) -> Optional[dict]:  # type: ignore[type-arg]
        """Return cached value if present and not expired, else None.

        Args:
            key: Cache lookup key.

        Returns:
            Deserialised dict, or None on miss/expiry.
        """
        try:
            cur = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            value_json, expires_at = row
            if time.time() > expires_at:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                logger.debug(f"Cache EXPIRED: {key}")
                return None
            logger.debug(f"Cache HIT: {key}")
            return json.loads(value_json)  # type: ignore[no-any-return]
        except sqlite3.Error as exc:
            raise CacheError(f"Cache get failed for key '{key}': {exc}") from exc

    # ------------------------------------------------------------------
    def set(self, key: str, value: dict, ttl_hours: int = 168) -> None:  # type: ignore[type-arg]
        """Store a value with an expiry time.

        Args:
            key: Cache key.
            value: JSON-serialisable dict.
            ttl_hours: Time-to-live in hours (default 168 = 1 week).
        """
        expires_at = time.time() + ttl_hours * 3600
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires_at),
            )
            self._conn.commit()
            logger.debug(f"Cache SET: {key} (TTL {ttl_hours}h)")
        except sqlite3.Error as exc:
            raise CacheError(f"Cache set failed for key '{key}': {exc}") from exc

    # ------------------------------------------------------------------
    def clear(self, source: Optional[str] = None) -> int:
        """Delete cache entries, optionally filtered by source prefix.

        Args:
            source: If given, only delete keys starting with ``"{source}:"``.

        Returns:
            Number of rows deleted.
        """
        try:
            if source:
                cur = self._conn.execute(
                    "DELETE FROM cache WHERE key LIKE ?", (f"{source}:%",)
                )
            else:
                cur = self._conn.execute("DELETE FROM cache")
            self._conn.commit()
            deleted = cur.rowcount
            logger.info(f"Cache cleared: {deleted} entries (source={source!r})")
            return deleted
        except sqlite3.Error as exc:
            raise CacheError(f"Cache clear failed: {exc}") from exc

    # ------------------------------------------------------------------
    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
