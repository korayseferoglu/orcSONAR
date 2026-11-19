"""SQLite-backed cache for API and BigWig responses."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from loguru import logger

from src.core.exceptions import CacheError

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key            TEXT PRIMARY KEY,
    value          TEXT NOT NULL,
    expires_at     REAL NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at);"

#: Version recorded with every entry a source writes. **Bump a source's number
#: whenever the meaning of its cached entries changes** — a corrected query, a
#: different coordinate convention, a new parser, a changed unit. Bumping makes
#: every entry written by the old code unusable; see :meth:`Cache.purge_stale`.
#:
#: Why this exists (roadmap B0): entries expire on time alone, and time is the
#: wrong axis. `clinvar_client` sends a literal `+AND+` that `requests`
#: percent-encodes, so the query returns zero variants, and those empty answers
#: are cached for 30 days. Fixing the two characters (`B1`) would leave the
#: pipeline serving the empty results for a month, and the obvious conclusion —
#: that the fix did not work — would be wrong.
#:
#: The source is the key's first colon-separated token, matching the documented
#: key format `{source}:{chrom}:{start}:{end}`. Versioning is deliberately
#: per-source: a single global number would force a full re-fetch of every
#: source on any bump — gnomAD at one request per second included — and a rule
#: that expensive is a rule people route around instead of following.
#:
#: A prefix that is not listed here gets `_DEFAULT_VERSION`, so a new source
#: works without ceremony; it earns an entry here the first time its meaning
#: changes. Two endpoints that need to be invalidated separately need two
#: prefixes, because the first token is all this sees.
#: The listed prefixes are the ones production actually writes, measured with
#: `git grep` over `src/` rather than guessed — a registry naming prefixes that
#: nothing uses would be exactly the decorative declaration invariant 3 is
#: about, and it would hide a prefix that was missing.
_SCHEMA_VERSIONS: dict[str, int] = {
    "bg": 1,  # transcriptome_fetcher: bg:canonical:{GENE}
    "ccle": 1,  # ccle_expression
    # v2 (B1): the query used to send `+AND+`, which reached E-utilities as a
    # literal plus, so every cached answer is an empty result set from a term
    # the server rejected. Those entries are not merely stale, they are
    # meaningless — this is the bump B0 was built for.
    "clinvar": 2,
    "encode_signal": 1,  # encode_reader: encode_signal:{file}:{chrom}:{start}:{end}
    "encode_url": 1,  # encode_reader: accession -> download URL
    "ensembl": 1,  # transcript_resolver, tss_mapper
    "gnomad": 1,  # gnomad_client
    "hic_contact": 1,  # hic_contacts: hic_contact:{uid}:{c1}:{bin1}:{c2}:{bin2}:{res}
    "phylop": 1,  # phylop_scorer
    "refseq": 1,  # transcript_resolver
    "rmsk": 1,  # repeat_scanner
    "seq": 1,  # transcript sequences
}

#: Version for a source with no entry above.
_DEFAULT_VERSION = 1

#: What a row written before versioning carries. It never matches a real
#: version, so those rows are stale by construction — which is the intended
#: reading: they were written by code that cached empty ClinVar answers and
#: zero-valued signals for failed reads, and their provenance is unknown.
_UNVERSIONED = 0


def source_of(key: str) -> str:
    """The source prefix a cache key belongs to.

    Args:
        key: Cache key, e.g. ``"clinvar:chr1:100:200"``.

    Returns:
        The first colon-separated token, or the whole key if it has none.
    """
    return key.split(":", 1)[0]


def current_version(source: str) -> int:
    """The schema version entries from this source must carry to be served.

    Args:
        source: Source prefix, e.g. ``"clinvar"``.

    Returns:
        The registered version, or :data:`_DEFAULT_VERSION`.
    """
    return _SCHEMA_VERSIONS.get(source, _DEFAULT_VERSION)


class Cache:
    """Thread-safe SQLite cache with TTL expiry.

    Key format: ``"{source}:{chrom}:{start}:{end}"``

    Args:
        db_path: Path to the SQLite database file.
    """

    #: The per-source schema versions, exposed for tests and for a deliberate
    #: bump. Same object as the module-level registry.
    SCHEMA_VERSIONS = _SCHEMA_VERSIONS

    # No default path. A caller that forgot to pass one silently opened the
    # live database even when the run was configured elsewhere — the deepest
    # instance of Bulgu 13, and the one that let phylop_scorer and ccle_reader
    # reach the wrong file (audit 2026-11-19). Making it required turns that
    # into an immediate TypeError instead of a wrong answer.
    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._migrate_schema_version()
        self._conn.commit()
        logger.debug(f"Cache initialised at {self._path}")

    # ------------------------------------------------------------------
    def _migrate_schema_version(self) -> None:
        """Add the version column to a database written before versioning.

        Existing rows get :data:`_UNVERSIONED`, which matches no real version,
        so they are stale by construction. That is deliberate: they were
        written by code whose behaviour is not known to match today's, and
        serving them is what roadmap B0 exists to prevent.

        Opening a cache is not the place for a full scan — call sites open one
        per region, so a purge here would be O(rows) per region. Staleness is
        enforced lazily in :meth:`get`; :meth:`purge_stale` does it in bulk
        when someone asks.
        """
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(cache)")}
        if "schema_version" in columns:
            return
        self._conn.execute(
            f"ALTER TABLE cache ADD COLUMN schema_version INTEGER NOT NULL DEFAULT {_UNVERSIONED}"
        )
        logger.warning(
            f"Cache at {self._path} predates schema versioning — its entries are "
            "now marked unversioned and will not be served (roadmap B0)"
        )

    # ------------------------------------------------------------------
    def get(self, key: str) -> dict | None:  # type: ignore[type-arg]
        """Return cached value if present and not expired, else None.

        Args:
            key: Cache lookup key.

        Returns:
            Deserialised dict, or None on miss/expiry.
        """
        try:
            cur = self._conn.execute(
                "SELECT value, expires_at, schema_version FROM cache WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            value_json, expires_at, stored_version = row
            wanted = current_version(source_of(key))
            if stored_version != wanted:
                # Written by a version of the code whose answers do not mean
                # the same thing. Deleted rather than skipped, so reverting a
                # bump cannot bring the old answer back (roadmap B0).
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                logger.warning(
                    f"Cache STALE: {key} written at schema v{stored_version}, "
                    f"now v{wanted} — dropped, will be re-fetched"
                )
                return None
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
        version = current_version(source_of(key))
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, expires_at, schema_version) "
                "VALUES (?, ?, ?, ?)",
                (key, json.dumps(value), expires_at, version),
            )
            self._conn.commit()
            logger.debug(f"Cache SET: {key} (TTL {ttl_hours}h, schema v{version})")
        except sqlite3.Error as exc:
            raise CacheError(f"Cache set failed for key '{key}': {exc}") from exc

    # ------------------------------------------------------------------
    def purge_stale(self) -> dict[str, int]:
        """Delete every entry whose schema version is not the current one.

        :meth:`get` already refuses a stale entry, so this is not needed for
        correctness. It is needed for **observability**: a silent purge is
        indistinguishable from a purge that never happened, and the count is
        what explains to someone re-running the pipeline why it went back to
        the network.

        Returns:
            Dropped row count per source, omitting sources with nothing stale.
        """
        dropped: dict[str, int] = {}
        try:
            rows = self._conn.execute("SELECT key, schema_version FROM cache").fetchall()
            stale_keys = [
                key for key, version in rows if version != current_version(source_of(key))
            ]
            for key in stale_keys:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                source = source_of(key)
                dropped[source] = dropped.get(source, 0) + 1
            self._conn.commit()
        except sqlite3.Error as exc:
            raise CacheError(f"Cache purge failed: {exc}") from exc
        if dropped:
            summary = ", ".join(f"{source}={count}" for source, count in sorted(dropped.items()))
            logger.warning(f"Cache purge: dropped {sum(dropped.values())} stale entries ({summary})")
        return dropped

    # ------------------------------------------------------------------
    def clear(self, source: str | None = None) -> int:
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

    def __enter__(self) -> Cache:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
