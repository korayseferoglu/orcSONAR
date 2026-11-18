"""Schema versioning and invalidation for the response cache (roadmap B0).

The cache keys responses by coordinate and expires them on time alone. Time is
the wrong axis for the failure that matters here: when the *meaning* of a
cached entry changes — a fixed query, a corrected coordinate convention, a
different parser — every stored entry is still "fresh" and keeps being served.

The case that forced this item: `clinvar_client` sends a literal `+AND+` which
`requests` percent-encodes, so the query returns **zero** variants (roadmap
`B1`). Those empty answers are cached with a 30-day TTL. Fix the two
characters and the pipeline keeps serving the empty results for a month, and
the obvious conclusion — which is wrong — is that the fix did not work.

So the cache has to know which version of the code wrote each entry, and an
entry written by a different version must not be served. These tests are about
that, not about TTL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.core.cache import Cache, current_version


@pytest.fixture
def db(tmp_path: Path) -> str:
    """A fresh cache database path."""
    return str(tmp_path / "cache.db")


def stored_rows(db_path: str) -> list[tuple]:
    """Raw rows, read without going through Cache."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT key, schema_version FROM cache").fetchall()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# the version travels with the entry
# --------------------------------------------------------------------------


def test_an_entry_records_the_version_that_wrote_it(db: str) -> None:
    """Without this there is nothing to compare against later."""
    with Cache(db) as cache:
        cache.set("clinvar:chr1:100:200", {"variants": []})
    assert stored_rows(db) == [("clinvar:chr1:100:200", current_version("clinvar"))]


def test_a_matching_version_is_still_a_hit(db: str) -> None:
    """Versioning must not break the ordinary case."""
    with Cache(db) as cache:
        cache.set("clinvar:chr1:100:200", {"variants": [1]})
        assert cache.get("clinvar:chr1:100:200") == {"variants": [1]}


def test_an_unregistered_source_round_trips(db: str) -> None:
    """A new prefix nobody has versioned yet must still work."""
    with Cache(db) as cache:
        cache.set("brandnew:chr1:1:2", {"x": 1})
        assert cache.get("brandnew:chr1:1:2") == {"x": 1}


# --------------------------------------------------------------------------
# a bumped version must not serve the old answer — B0's acceptance criterion
# --------------------------------------------------------------------------


def test_a_bumped_version_turns_a_hit_into_a_miss(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: after a bump, yesterday's answer is not served.

    This is the B1 scenario. The entry below stands for an empty ClinVar
    response cached before the query was fixed.
    """
    with Cache(db) as cache:
        cache.set("clinvar:chr1:100:200", {"variants": []})

    monkeypatch.setitem(Cache.SCHEMA_VERSIONS, "clinvar", current_version("clinvar") + 1)

    with Cache(db) as cache:
        assert cache.get("clinvar:chr1:100:200") is None


def test_a_stale_entry_is_deleted_not_merely_skipped(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Skipping would leave it to be served again if a bump were reverted."""
    with Cache(db) as cache:
        cache.set("clinvar:chr1:100:200", {"variants": []})

    monkeypatch.setitem(Cache.SCHEMA_VERSIONS, "clinvar", current_version("clinvar") + 1)
    with Cache(db) as cache:
        cache.get("clinvar:chr1:100:200")

    assert stored_rows(db) == []


def test_a_bump_leaves_other_sources_alone(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalidation has to be per source, or nobody will ever bump it.

    A global version would force a full re-fetch of every source — gnomAD at
    one request per second included — and a rule that expensive gets avoided
    rather than followed.
    """
    with Cache(db) as cache:
        cache.set("clinvar:chr1:100:200", {"variants": []})
        cache.set("rmsk:chr1:100:200", {"entries": []})

    monkeypatch.setitem(Cache.SCHEMA_VERSIONS, "clinvar", current_version("clinvar") + 1)
    with Cache(db) as cache:
        assert cache.get("clinvar:chr1:100:200") is None
        assert cache.get("rmsk:chr1:100:200") == {"entries": []}


# --------------------------------------------------------------------------
# entries written before versioning existed
# --------------------------------------------------------------------------


def test_an_old_database_is_migrated_not_rejected(db: str) -> None:
    """Opening a pre-versioning database must work, not crash."""
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)")
    conn.execute("INSERT INTO cache VALUES ('clinvar:chr1:1:2', '{\"variants\": []}', 1e11)")
    conn.commit()
    conn.close()

    with Cache(db) as cache:
        assert cache.get("rmsk:chr1:1:2") is None  # unrelated key, just exercises the open


def test_pre_versioning_entries_are_not_served(db: str) -> None:
    """They were written by code whose behaviour is unknown.

    Every entry in the cache before this item was written by a version that,
    among other things, cached empty ClinVar answers and zero-valued signals
    for failed reads. Serving them is the exact thing B0 exists to stop, so
    the unversioned rows count as stale.
    """
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)")
    conn.execute("INSERT INTO cache VALUES ('clinvar:chr1:1:2', '{\"variants\": []}', 1e11)")
    conn.commit()
    conn.close()

    with Cache(db) as cache:
        assert cache.get("clinvar:chr1:1:2") is None


# --------------------------------------------------------------------------
# the invalidation has to be observable
# --------------------------------------------------------------------------


def test_every_inline_cache_prefix_is_registered() -> None:
    """A prefix nobody registered silently gets the default version forever.

    That is survivable but invisible: the day its meaning changes, there is no
    number to bump and the stale answers keep being served. This walks `src/`
    for the inline keys and checks each prefix has an entry, so adding a source
    without registering it fails here rather than three months later.
    """
    import re

    src = Path(__file__).resolve().parents[2] / "src"
    # Two shapes, both needed. The first version of this test only looked for
    # the inline one and passed while `hic_contact` — 83 rows in the live
    # database — was unregistered; the gap showed up in the cache file, not
    # here. Keys built inside a `*cache_key*` helper are the second shape.
    inline = re.compile(r"""cache(?:_key)?\s*(?:=|\.(?:get|set)\()\s*f?["']([a-z0-9_]+):""")
    helper = re.compile(
        r"""def\s+[A-Za-z_]*cache_key[A-Za-z_]*\s*\(.*?return\s+f["']([a-z0-9_]+):""",
        re.DOTALL,
    )
    found: dict[str, str] = {}
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for prefix in inline.findall(text) + helper.findall(text):
            found.setdefault(prefix, str(path.relative_to(src.parent)))
    assert found, "the scan found no cache keys at all — the pattern has rotted"
    for expected in ("clinvar", "encode_signal", "hic_contact"):
        assert expected in found, f"the scan no longer sees {expected} — it has rotted"
    missing = {p: where for p, where in found.items() if p not in Cache.SCHEMA_VERSIONS}
    assert not missing, f"unregistered cache prefixes: {missing}"


def test_purging_reports_what_it_dropped(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A silent purge is indistinguishable from a purge that did not happen.

    The count is what tells someone re-running the pipeline why it suddenly
    went back to the network.
    """
    with Cache(db) as cache:
        cache.set("clinvar:chr1:1:2", {"variants": []})
        cache.set("clinvar:chr1:3:4", {"variants": []})
        cache.set("rmsk:chr1:1:2", {"entries": []})

    monkeypatch.setitem(Cache.SCHEMA_VERSIONS, "clinvar", current_version("clinvar") + 1)
    with Cache(db) as cache:
        dropped = cache.purge_stale()

    assert dropped == {"clinvar": 2}, dropped
    assert [key for key, _ in stored_rows(db)] == ["rmsk:chr1:1:2"]
