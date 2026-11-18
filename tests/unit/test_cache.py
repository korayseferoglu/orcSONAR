"""Unit tests for src/core/cache.py."""

import sqlite3
from unittest.mock import MagicMock

import pytest

from src.core.cache import Cache
from src.core.exceptions import CacheError


class TestCache:
    def test_set_and_get(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            cache.set("ensembl:chr1:100:200", {"foo": "bar"})
            result = cache.get("ensembl:chr1:100:200")
            assert result == {"foo": "bar"}

    def test_miss_returns_none(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            assert cache.get("nonexistent:key") is None

    def test_expiry(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            # TTL = 0 hours → already expired
            cache.set("gnomad:chrX:500:600", {"af": 0.001}, ttl_hours=0)
            # Give SQLite a moment then check
            result = cache.get("gnomad:chrX:500:600")
            assert result is None

    def test_overwrite(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            cache.set("k562:chr2:1000:2000", {"v": 1})
            cache.set("k562:chr2:1000:2000", {"v": 99})
            assert cache.get("k562:chr2:1000:2000") == {"v": 99}

    def test_clear_all(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            cache.set("a:chr1:0:1", {"x": 1})
            cache.set("b:chr2:0:1", {"y": 2})
            deleted = cache.clear()
            assert deleted == 2
            assert cache.get("a:chr1:0:1") is None

    def test_clear_by_source(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            cache.set("ensembl:chr1:0:1", {"x": 1})
            cache.set("cosmic:chr1:0:1", {"y": 2})
            deleted = cache.clear(source="ensembl")
            assert deleted == 1
            assert cache.get("cosmic:chr1:0:1") == {"y": 2}

    def test_key_format(self, tmp_cache_db):
        """Key format: '{source}:{chrom}:{start}:{end}'"""
        with Cache(tmp_cache_db) as cache:
            key = "phylop:chr6:43768652:43769652"
            cache.set(key, {"score": 3.14})
            assert cache.get(key)["score"] == pytest.approx(3.14)

    # --- SQLite error paths (lines 70-71, 90-91, 114-115) ---
    # sqlite3.Connection.execute is C-level read-only in Python 3.12+,
    # so we replace the entire _conn with a MagicMock after normal init.

    def test_get_sqlite_error_raises_cache_error(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.Error("disk full")
            cache._conn = mock_conn
            with pytest.raises(CacheError, match="Cache get failed"):
                cache.get("any:key")

    def test_set_sqlite_error_raises_cache_error(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.Error("locked")
            cache._conn = mock_conn
            with pytest.raises(CacheError, match="Cache set failed"):
                cache.set("any:key", {"v": 1})

    def test_clear_sqlite_error_raises_cache_error(self, tmp_cache_db):
        with Cache(tmp_cache_db) as cache:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.Error("readonly")
            cache._conn = mock_conn
            with pytest.raises(CacheError, match="Cache clear failed"):
                cache.clear()
