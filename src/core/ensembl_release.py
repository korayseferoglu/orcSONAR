"""The one place that knows which Ensembl release a run reads.

Roadmap B17. Until this module existed the project called
``https://rest.ensembl.org`` — "whatever is current" — and nothing recorded
which release answered. That is not a theoretical reproducibility gap. It was
measured on 2026-11-27: the SQLite cache held cDNA from **two** releases at
once, because TTLs expire per entry and each refetch landed on whatever was
live that day. Six transcripts matched release 116 only; eight matched 113/115
only; the fetches were six months apart. The sequences genuinely differ —
VEGFA's ``ENST00000372067`` is 3535 nt in releases 113-115 and 3537 nt in 116,
and ``ENST00000377970`` is 2351 nt in the cache against 3868 nt live, which is
1517 extra nucleotides of search space for a 7-mer seed scan.

Three mechanisms, deliberately separate because they fail differently:

**The pin is the host.** Ensembl REST refuses versioned accessions
(``/sequence/id/ENST00000372067.8`` → *ID not found*), so a release cannot be
pinned per request; it has to be the hostname. Archive hosts are
``https://<mon><yyyy>.rest.ensembl.org`` and Ensembl keeps them for five
years.

A release only gets an archive host once it has been **superseded** — when
this was written 115 was archived at ``sep2025`` while 116 was live with no
archive host at all. Hence the pin rule: *the newest release that has a
resolvable archive host*. Pinning to the live host would be a URL that
silently starts meaning the next release. The cost is explicit and recorded:
115 is one release behind, and 116 contains a correction to the VEGFA
transcript. A pinned run reproduces the computation, not the biology — moving
the pin is a deliberate act with a known consequence (re-fetch, re-run), which
is exactly what it should be.

**The release is in the cache key.** A schema-version bump
(`cache._SCHEMA_VERSIONS`, the mechanism `B0` built and `B1` used for ClinVar)
would invalidate today's mixed entries once — but it depends on someone
remembering to bump it the next time the pin moves. A release inside the key
makes two releases unable to share an entry *by construction*. This project's
recurring failure is a rule that was declared and not enforced (invariant 3),
so where a mechanism and a rule are both available, the mechanism wins.

**The check is loud.** If the pinned host answers with a release the config
does not declare, the run raises. If the host cannot be reached at all, that is
*unverified*, not a mismatch: a transient network failure must not look like a
changed release, and it must not pass in silence either — the run manifest
records ``release_verified: false`` so the run says what it could not confirm.
"""

from __future__ import annotations

import re
from typing import Any

#: Archive hosts look like `sep2025.rest.ensembl.org`. The month-year is the
#: archive's own label, not the release number, so the release is read from the
#: host's `/info/data` rather than parsed out of the name — the two are only
#: related by Ensembl's release calendar, and guessing that mapping would be a
#: second copy of a fact Ensembl already serves.
_ARCHIVE_HOST = re.compile(
    r"^https?://(?P<stamp>[a-z]{3}\d{4})\.rest\.ensembl\.org/?$", re.I
)


class ReleaseMismatch(RuntimeError):
    """The pinned host served a release the configuration does not declare."""


def host_is_archived(base_url: str) -> bool:
    """Whether ``base_url`` pins a release instead of following the current one.

    Args:
        base_url: The configured Ensembl REST base URL.

    Returns:
        ``True`` for an archive host, ``False`` for ``rest.ensembl.org`` —
        which is not a pin at all, but "whatever is current".
    """
    return _ARCHIVE_HOST.match(base_url.strip()) is not None


def release_in_host(base_url: str) -> str | None:
    """The archive stamp in ``base_url``, e.g. ``"sep2025"``.

    Args:
        base_url: The configured Ensembl REST base URL.

    Returns:
        The stamp, or ``None`` when the URL is not an archive host.
    """
    match = _ARCHIVE_HOST.match(base_url.strip())
    return match.group("stamp").lower() if match else None


def cache_key(prefix: str, release: int, rest: str) -> str:
    """Build a cache key that cannot be shared across releases.

    The release goes **after** the source prefix so `cache.source_of` — which
    reads the first colon-separated token and decides the schema version from
    it — keeps working unchanged.

    Args:
        prefix: Source prefix, e.g. ``"seq"``, ``"bg"``, ``"ensembl"``.
        release: Ensembl release number the value came from.
        rest: The rest of the key, e.g. a transcript id or ``"canonical:ACTB"``.

    Returns:
        ``"{prefix}:{release}:{rest}"``.
    """
    return f"{prefix}:{release}:{rest}"


def verify(*, declared: int, live: int | None) -> None:
    """Raise when the host serves a release the config does not declare.

    Args:
        declared: Release number from the configuration.
        live: Release the host reported, or ``None`` if it could not be read.

    Raises:
        ReleaseMismatch: When ``live`` is a different release.

    An unreachable host is **not** an error here. It is unverified, which
    :func:`verified` reports and the run manifest records; failing a whole run
    on a transient 503 would make the pin a liability rather than a guarantee.
    """
    if live is None:
        return None
    if live != declared:
        raise ReleaseMismatch(
            f"Ensembl release mismatch: config declares {declared}, the pinned "
            f"host answered {live}. Every cached sequence is keyed on "
            f"{declared}, so continuing would compute on one release while "
            f"recording another. Fix the pin (and expect a re-fetch), or fix "
            f"the declared release — do not ignore this (roadmap B17)."
        )
    return None


def verified(*, declared: int, live: int | None) -> bool:
    """Whether the declared release was actually confirmed against the host.

    Args:
        declared: Release number from the configuration.
        live: Release the host reported, or ``None``.

    Returns:
        ``True`` only when the host confirmed it. ``False`` means *not
        checked*, which the manifest records rather than implying a check that
        did not happen.
    """
    return live is not None and live == declared


def live_release(base_url: str, timeout: float = 15.0) -> int | None:
    """Ask the host which release it serves.

    Args:
        base_url: Ensembl REST base URL.
        timeout: Seconds to wait.

    Returns:
        The release number, or ``None`` when it could not be read. Every
        failure mode collapses to ``None`` on purpose: the caller's question is
        "can I confirm the release?", and a 503, a timeout and a reshaped
        payload all answer it the same way.
    """
    import requests

    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/info/data",
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        releases = response.json().get("releases") or []
    except Exception:  # noqa: BLE001 - any failure is "could not confirm"
        return None
    try:
        return int(releases[0])
    except (IndexError, TypeError, ValueError):
        return None


def describe(base_url: str, declared: int, *, check: bool = False) -> dict[str, Any]:
    """The provenance block the run manifest records for Ensembl.

    Args:
        base_url: Configured base URL.
        declared: Configured release.
        check: Whether to ask the host. The manifest writer passes ``False``
            by default so writing a manifest never depends on the network;
            the pipeline's own startup check is what sets this.

    Returns:
        A JSON-serialisable record.
    """
    live = live_release(base_url) if check else None
    return {
        "base_url": base_url,
        "release": declared,
        "pinned": host_is_archived(base_url),
        "release_verified": verified(declared=declared, live=live) if check else False,
        "live_release": live,
    }
