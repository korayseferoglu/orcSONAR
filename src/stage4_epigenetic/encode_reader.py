"""ENCODE BigWig signal reader — base class for Stage 4 epigenetic modules.

Resolves ENCODE file accessions to download URLs via the ENCODE REST API,
then streams per-region signal from remote BigWig files using pyBigWig.
All URL lookups and BigWig signals are cached in SQLite.

Return value convention:
  - Raw float from BigWig (RPKM / fold-enrichment / RPM depending on track).
  - 0.0 on any read failure (neutral for open-chromatin marks).
  - Callers (Stage 7 scoring engine) are responsible for [0, 1] normalisation.

ENCODE API quirk:
  GET /files/{accession}/?format=json
  → cloud_metadata.url  (S3 pre-signed, preferred)
  → href                (relative path, constructed to absolute)
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pyBigWig
import requests
import yaml
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion

#: What a read returns when nothing was measured: an open unknown, not a
#: number (roadmap B2, AUDIT.md Bulgu-10).
#:
#: This replaced `_NEUTRAL_SIGNAL = 0.0`, which six modules reached — ATAC, the
#: three histone marks, nascent transcription, and Ago2/RBP eCLIP. For every
#: one of those, *less signal means lower risk*, so substituting a zero on
#: failure did not make a site neutral. It made it look **safe**, and a wholly
#: dead source produced plausible output instead of an error. Writing 0.5 here
#: would not have helped either: this is raw-signal space in native units,
#: while the documented 0.5 contract lives in score space.
#:
#: `None` forces every consumer to say what it does with an unknown. The
#: mergers exclude the channel and renormalise; roadmap `B3` adds the coverage
#: threshold that refuses to score a site when too little is known.
UNKNOWN_SIGNAL: None = None
_ENCODE_URL_TTL_HOURS: int = 720   # 30 days — accession→URL mapping rarely changes
_SIGNAL_TTL_HOURS: int = 168       # 1 week — BigWig signal
_DEFAULT_CELL_LINES_YAML: str = "config/cell_lines.yaml"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _resolve_encode_redirect(url: str) -> str:
    """Resolve the ENCODE portal 307 to its short-lived signed S3 URL.

    pyBigWig (libBigWig) does not follow HTTP redirects, so an
    ``encodeproject.org/files/.../*.bigWig`` URL fails to open. We issue a
    HEAD-like GET (no follow) and return the ``Location`` header.

    Non-ENCODE URLs and URLs that don't redirect are returned unchanged.
    """
    if "encodeproject.org" not in url:
        return url
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(url, timeout=20)
        return url
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            location = exc.headers.get("Location")
            if location:
                return location
        logger.warning(
            f"encode_reader: ENCODE returned {exc.code} for {url[:80]} (no Location)"
        )
        return url
    except Exception as exc:
        logger.warning(f"encode_reader: redirect resolve failed for {url[:80]}: {exc}")
        return url


# ---------------------------------------------------------------------------
# Module-level BigWig helpers (reused by both single and bulk reads)
# ---------------------------------------------------------------------------


# pyBigWig ships no stubs, so the handle is Any rather than object: typing it
# as object made every attribute access an error, which is noise that hides
# the real ones (roadmap B2a).
def _bigwig_mean(bw: Any, chrom: str, start: int, end: int) -> float | None:
    """Read mean signal for one region from an open pyBigWig handle.

    Args:
        bw: Open pyBigWig handle.
        chrom: Chromosome with ``chr`` prefix (e.g. ``"chr6"``).
        start: 0-based start coordinate (inclusive).
        end: 0-based end coordinate (exclusive).

    Returns:
        Mean signal; 0.0 when the contig is present but silent, ``None`` when
        nothing could be measured (missing contig, or any error).
    """
    try:
        stats = bw.stats(chrom, start, end, type="mean")
        value = stats[0] if stats else None
        if value is not None:
            return float(value)
        # No intervals in the range. Two very different causes, and collapsing
        # them is what made a broken query look like a quiet locus (B2):
        #   * the file has this contig and records nothing here — a real zero,
        #   * the file does not have this contig at all — nothing was measured,
        #     and a "chr" prefix mismatch lands exactly here.
        try:
            contigs = bw.chroms()
        except Exception as exc:  # noqa: BLE001 - any failure here is an unknown
            logger.warning(f"encode_reader: contig list unreadable for '{chrom}': {exc}")
            return UNKNOWN_SIGNAL
        if not isinstance(contigs, dict):
            logger.warning(
                f"encode_reader: contig list is {type(contigs).__name__}, not a mapping — "
                f"cannot tell whether {chrom} exists, so {chrom}:{start}-{end} is UNKNOWN"
            )
            return UNKNOWN_SIGNAL
        if chrom not in contigs:
            logger.warning(
                f"encode_reader: {chrom} is not a contig in this BigWig "
                f"({len(contigs)} contigs, e.g. {sorted(contigs)[:3]}) — "
                f"{chrom}:{start}-{end} is UNKNOWN, not zero"
            )
            return UNKNOWN_SIGNAL
        logger.debug(f"encode_reader: no intervals in {chrom}:{start}-{end} — measured zero")
        return 0.0
    except Exception as exc:
        logger.warning(f"encode_reader: stats failed {chrom}:{start}-{end}: {exc}")
        return UNKNOWN_SIGNAL


def _signal_cache_key(url: str, region: GenomicRegion) -> str:
    """Build a stable SQLite cache key for one (URL, region) pair.

    Uses the filename portion of the URL as the URL identifier so the key
    remains readable and unique without hashing.

    Args:
        url: BigWig download URL.
        region: Genomic interval.

    Returns:
        Cache key string in the form ``encode_signal:{file_id}:{chrom}:{start}:{end}``.
    """
    # Extract accession/filename from URL tail: ".../ENCFF492CEJ.bigWig" → "ENCFF492CEJ"
    tail = url.rstrip("/").split("/")[-1]
    file_id = tail.split(".")[0] if "." in tail else tail
    return f"encode_signal:{file_id}:{region.chrom}:{region.start}:{region.end}"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class EncodeSignalReader:
    """Base class for reading epigenetic signal tracks from ENCODE BigWig files.

    Supports two URL sources:
    1. **Direct URL** from ``config/cell_lines.yaml`` — no API call needed.
    2. **Accession-based** resolution via the ENCODE REST API — useful when
       only the accession (e.g. ``"ENCFF492CEJ"``) is known.

    All resolved URLs and BigWig signal readings are cached in the shared
    SQLite database to avoid redundant network traffic.

    Args:
        config: Pipeline configuration (provides cache DB path, ENCODE URL).
        cell_lines_yaml: Path to cell_lines.yaml.
    """

    def __init__(
        self,
        config: OrcSonarConfig,
        cell_lines_yaml: str | Path = _DEFAULT_CELL_LINES_YAML,
    ) -> None:
        self._config = config
        self._cache_db = config.data_paths.cache_db
        self._encode_base = config.encode_portal_url.rstrip("/")
        self._cell_lines: dict = self._load_cell_lines(Path(cell_lines_yaml))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_file_url(self, file_accession: str) -> str:
        """Resolve an ENCODE file accession to an absolute BigWig download URL.

        Checks the SQLite cache first; calls the ENCODE REST API on a miss
        with exponential-backoff retry (3 attempts).

        Args:
            file_accession: ENCODE accession, e.g. ``"ENCFF492CEJ"``.

        Returns:
            Absolute BigWig download URL.

        Raises:
            ValueError: If the API response contains no recognisable URL field.
            requests.HTTPError: If ENCODE returns a non-2xx status after retries.
        """
        cache_key = f"encode_url:{file_accession}"
        with Cache(self._cache_db) as cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"encode_reader: URL cache HIT for {file_accession}")
                return str(cached["url"])
            url = self._download_url_for_accession(file_accession)
            cache.set(cache_key, {"url": url}, ttl_hours=_ENCODE_URL_TTL_HOURS)
            logger.info(f"encode_reader: resolved {file_accession} → {url}")
            return url

    def read_signal(self, url: str, region: GenomicRegion) -> float | None:
        """Read mean BigWig signal for a single genomic region.

        Opens and closes the BigWig handle per call.  Use ``read_signal_bulk``
        when reading many regions from the same track to avoid repeated
        network-round-trip overhead.

        Args:
            url: Direct BigWig URL or local path.
            region: Genomic interval (chr-prefixed, hg38).

        Returns:
            Mean signal value (raw, not normalised), or ``UNKNOWN_SIGNAL``
            when nothing could be measured.
        """
        cache_key = _signal_cache_key(url, region)
        with Cache(self._cache_db) as cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"encode_reader: signal cache HIT {cache_key}")
                value = cached.get("signal")
                return None if value is None else float(value)

            signal = _read_one_region(url, region)
            # An unknown is not a measurement and is deliberately NOT cached.
            # Caching it would remember a transient network failure for
            # `_SIGNAL_TTL_HOURS` and serve it as though the locus had been
            # examined — the same "a failure becomes a finding" shape as
            # roadmap B0, where a stale empty ClinVar answer outlives its fix.
            if signal is not None:
                cache.set(cache_key, {"signal": signal}, ttl_hours=_SIGNAL_TTL_HOURS)

        shown = "ÖLÇÜLMEDİ" if signal is None else f"{signal:.4f}"
        logger.debug(f"encode_reader: {region} signal={shown} url={url[:60]}")
        return signal

    def read_signal_bulk(
        self, url: str, regions: list[GenomicRegion]
    ) -> list[float | None]:
        """Read mean BigWig signal for multiple regions with a single open call.

        Checks the cache per region; issues BigWig reads only for misses.
        The BigWig handle is opened once across all cache misses.

        Args:
            url: Direct BigWig URL or local path.
            regions: Genomic intervals (chr-prefixed, hg38).

        Returns:
            Signal values in the same order as ``regions``; ``None`` where
            nothing could be measured (roadmap B2).
        """
        if not regions:
            return []

        results: list[float | None] = [UNKNOWN_SIGNAL] * len(regions)
        miss_indices: list[int] = []

        with Cache(self._cache_db) as cache:
            for i, region in enumerate(regions):
                key = _signal_cache_key(url, region)
                hit = cache.get(key)
                if hit is not None and hit.get("signal") is not None:
                    results[i] = float(hit["signal"])
                elif hit is not None:
                    # A null already in the cache (written before unknowns
                    # stopped being cached, below). Read it back as unknown
                    # rather than through float(None), which raises.
                    results[i] = UNKNOWN_SIGNAL
                else:
                    miss_indices.append(i)

            if not miss_indices:
                return results

            try:
                bw = pyBigWig.open(_resolve_encode_redirect(url))
            except Exception as exc:
                logger.error(f"encode_reader: cannot open BigWig '{url}': {exc}")
                return results  # cache-miss positions stay at neutral

            try:
                for i in miss_indices:
                    region = regions[i]
                    signal = _bigwig_mean(bw, region.chrom, region.start, region.end)
                    results[i] = signal
                    # An unknown is not a measurement, so it is not cached:
                    # caching it would serve a transient failure as "this
                    # locus was examined" for the whole TTL. B2's roadmap
                    # entry states this contract; the bulk path did not keep
                    # it (audit 2026-11-19). A measured 0.0 *is* information
                    # and is still cached.
                    if signal is not None:
                        key = _signal_cache_key(url, region)
                        cache.set(key, {"signal": signal}, ttl_hours=_SIGNAL_TTL_HOURS)
                    # Formatting an unknown with `:.4f` raises, which killed
                    # the entire bulk read on the first unmeasured region.
                    shown = "ÖLÇÜLMEDİ" if signal is None else f"{signal:.4f}"
                    logger.debug(f"encode_reader: {region} signal={shown}")
            finally:
                bw.close()

        return results

    # ------------------------------------------------------------------
    # Protected helpers (used by subclasses)
    # ------------------------------------------------------------------

    def _get_url_for_cell_line(
        self, cell_line: str, signal_type: str
    ) -> str | None:
        """Look up a BigWig URL from the loaded cell_lines.yaml.

        Args:
            cell_line: Cell line name, e.g. ``"HeLa"``.
            signal_type: YAML key, e.g. ``"atac_seq"`` or ``"h3k4me3_chip"``.

        Returns:
            URL string, or ``None`` if the cell line or key is absent/null.
        """
        cell_data = self._cell_lines.get(cell_line)
        if cell_data is None:
            logger.warning(
                f"encode_reader: cell line '{cell_line}' not in cell_lines.yaml"
            )
            return None
        url = cell_data.get(signal_type)
        if not url:
            logger.warning(
                f"encode_reader: '{signal_type}' not configured for {cell_line}"
            )
            return None
        return str(url)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _load_cell_lines(yaml_path: Path) -> dict:
        """Parse cell_lines.yaml into a nested dict.

        Args:
            yaml_path: Path to the YAML file.

        Returns:
            ``{cell_line: {signal_type: url, ...}, ...}``
        """
        if not yaml_path.exists():
            logger.warning(f"encode_reader: cell_lines.yaml not found at {yaml_path}")
            return {}
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        return data  # type: ignore[return-value]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _download_url_for_accession(self, accession: str) -> str:
        """Call the ENCODE REST API to retrieve the BigWig download URL.

        Prefers ``cloud_metadata.url`` (S3); falls back to constructing an
        absolute URL from ``href``.

        Args:
            accession: ENCODE file accession.

        Returns:
            Absolute download URL.

        Raises:
            requests.HTTPError: On non-2xx response (triggers tenacity retry).
            ValueError: If neither ``cloud_metadata.url`` nor ``href`` is present.
        """
        api_url = f"{self._encode_base}/files/{accession}/?format=json"
        resp = requests.get(
            api_url, timeout=30, headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()

        cloud = data.get("cloud_metadata") or {}
        s3_url = cloud.get("url")
        if s3_url:
            return str(s3_url)

        href = data.get("href")
        if href:
            return f"{self._encode_base}{href}"

        raise ValueError(
            f"encode_reader: no URL in ENCODE API response for accession '{accession}'"
        )


# ---------------------------------------------------------------------------
# Internal single-region helper (used by read_signal)
# ---------------------------------------------------------------------------


def _read_one_region(url: str, region: GenomicRegion) -> float | None:
    """Open a BigWig, read one region, close it, return the mean signal.

    Args:
        url: BigWig URL or local path.
        region: Target genomic interval.

    Returns:
        Mean signal float, or ``None`` when nothing could be measured.
    """
    try:
        bw = pyBigWig.open(_resolve_encode_redirect(url))
    except Exception as exc:
        logger.error(f"encode_reader: cannot open BigWig '{url}': {exc}")
        return UNKNOWN_SIGNAL
    try:
        return _bigwig_mean(bw, region.chrom, region.start, region.end)
    finally:
        bw.close()
