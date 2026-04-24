"""Hi-C 3D genome contact reader for Stage 4.

Queries contact frequency between a saRNA target region and each off-target
candidate using the hic-straw library against 4DN-portal .hic files.

Contact semantics:
  High contact frequency between an off-target locus and the saRNA target
  promoter → the two regions are spatially proximal → off-target engagement
  risk is elevated (chromatin looping can bring distal enhancers or silenced
  regions into functional proximity).

Return value convention:
  - Raw KR-normalised contact count (float).  Stage 7 normalises to [0, 1].
  - 0.0 (neutral) when the .hic URL is absent, the region has no coverage,
    or on any read failure.

Hicstraw notes:
  - hic-straw must be compiled with libcurl; it is an optional dependency.
  - The call is isolated in ``_call_straw`` so tests can patch it without
    needing hicstraw installed.
  - Chromosome strings are passed WITHOUT the "chr" prefix (e.g. "6", "X").
  - KR normalisation is tried first; falls back to NONE on failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, HiCResult

_NEUTRAL_CONTACT: float = 0.0
_HIC_TTL_HOURS: int = 720          # 30 days — .hic data rarely changes
_DEFAULT_CELL_LINES_YAML: str = "config/cell_lines.yaml"
_DEFAULT_RESOLUTION: int = 25_000  # 25 kb bin


def _round_bin(pos: int, resolution: int) -> int:
    """Snap a position to the nearest lower bin boundary."""
    return (pos // resolution) * resolution


def _contact_cache_key(
    hic_url: str, r1: GenomicRegion, r2: GenomicRegion, resolution: int
) -> str:
    """Build a stable cache key for a contact query.

    Args:
        hic_url: URL of the .hic file.
        r1: First genomic region.
        r2: Second genomic region.
        resolution: Bin size in bp.

    Returns:
        Key string ``hic_contact:{uid}:{c1}:{bin1}:{c2}:{bin2}:{res}``.
    """
    tail = hic_url.rstrip("/").split("/")[-1]
    uid = tail.split(".")[0] if "." in tail else tail
    b1 = _round_bin(r1.start, resolution)
    b2 = _round_bin(r2.start, resolution)
    c1 = r1.chrom.lstrip("chr")
    c2 = r2.chrom.lstrip("chr")
    return f"hic_contact:{uid}:{c1}:{b1}:{c2}:{b2}:{resolution}"


class HiCContactReader:
    """Reads Hi-C contact frequency between genomic region pairs.

    Uses the hic-straw library to query remote 4DN-portal .hic files.
    Results are cached in SQLite (30-day TTL).

    Args:
        config: Pipeline configuration (provides cache DB path).
        cell_lines_yaml: Path to cell_lines.yaml (``hic_url`` key per cell line).
    """

    def __init__(
        self,
        config: OrcSonarConfig,
        cell_lines_yaml: str | Path = _DEFAULT_CELL_LINES_YAML,
    ) -> None:
        self._config = config
        self._cache_db = config.data_paths.cache_db
        self._cell_lines: dict = self._load_cell_lines(Path(cell_lines_yaml))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_contact(
        self,
        target: GenomicRegion,
        offtarget: GenomicRegion,
        cell_line: str,
        resolution: int = _DEFAULT_RESOLUTION,
    ) -> HiCResult:
        """Return Hi-C contact frequency between two genomic regions.

        Args:
            target: saRNA target region (e.g. promoter window).
            offtarget: Off-target candidate region.
            cell_line: Cell line name, e.g. ``"HeLa"``.
            resolution: Hi-C bin size in bp (default 25 000).

        Returns:
            HiCResult with ``contact_frequency`` set to 0.0 when not
            configured or on any read failure.
        """
        url = self._get_hic_url(cell_line)
        if url is None:
            return HiCResult(
                target_region=target,
                offtarget_region=offtarget,
                contact_frequency=_NEUTRAL_CONTACT,
            )

        cache_key = _contact_cache_key(url, target, offtarget, resolution)
        with Cache(self._cache_db) as cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"hic_contacts: cache HIT {cache_key}")
                return HiCResult(
                    target_region=target,
                    offtarget_region=offtarget,
                    contact_frequency=float(cached["contact"]),
                )

            freq = self._fetch_contact_frequency(url, target, offtarget, resolution)
            cache.set(cache_key, {"contact": freq}, ttl_hours=_HIC_TTL_HOURS)

        logger.debug(
            f"hic_contacts: {target} ↔ {offtarget} contact={freq:.4f} "
            f"cell={cell_line}"
        )
        return HiCResult(
            target_region=target,
            offtarget_region=offtarget,
            contact_frequency=freq,
        )

    def get_contacts_bulk(
        self,
        target: GenomicRegion,
        offtargets: list[GenomicRegion],
        cell_line: str,
        resolution: int = _DEFAULT_RESOLUTION,
    ) -> list[HiCResult]:
        """Return Hi-C contact frequencies for a target against multiple off-targets.

        Args:
            target: saRNA target region.
            offtargets: Off-target candidate regions.
            cell_line: Cell line name.
            resolution: Hi-C bin size in bp (default 25 000).

        Returns:
            List of HiCResult in the same order as ``offtargets``.
        """
        return [
            self.get_contact(target, offt, cell_line, resolution)
            for offt in offtargets
        ]

    # ------------------------------------------------------------------
    # Protected helpers
    # ------------------------------------------------------------------

    def _get_hic_url(self, cell_line: str) -> Optional[str]:
        """Look up the .hic URL for a cell line.

        Args:
            cell_line: Cell line name.

        Returns:
            URL string, or ``None`` if absent or null.
        """
        cell_data = self._cell_lines.get(cell_line)
        if cell_data is None:
            logger.warning(f"hic_contacts: '{cell_line}' not in cell_lines.yaml")
            return None
        url = cell_data.get("hic_url")
        if not url:
            logger.warning(f"hic_contacts: hic_url not configured for {cell_line}")
            return None
        return str(url)

    def _fetch_contact_frequency(
        self,
        url: str,
        r1: GenomicRegion,
        r2: GenomicRegion,
        resolution: int,
    ) -> float:
        """Query hicstraw for the contact count between two bins.

        Strips the ``chr`` prefix from chromosome names before calling straw
        (the 4DN .hic convention uses bare chromosome labels like ``"6"``).
        Tries KR normalisation first, falls back to NONE.

        Args:
            url: Remote .hic file URL.
            r1: First region.
            r2: Second region.
            resolution: Bin size in bp.

        Returns:
            Contact frequency float, or 0.0 on failure.
        """
        c1 = r1.chrom.lstrip("chr")
        c2 = r2.chrom.lstrip("chr")
        reg1 = f"{c1}:{r1.start}:{r1.end}"
        reg2 = f"{c2}:{r2.start}:{r2.end}"
        target_bin_x = _round_bin(r1.start, resolution)
        target_bin_y = _round_bin(r2.start, resolution)

        for norm in ("KR", "NONE"):
            try:
                records = self._call_straw(url, norm, reg1, reg2, resolution)
            except Exception as exc:
                logger.warning(f"hic_contacts: straw({norm}) failed for {reg1}↔{reg2}: {exc}")
                continue

            if not records:
                continue

            for rec in records:
                if rec.binX == target_bin_x and rec.binY == target_bin_y:
                    return float(rec.counts)

            # No exact bin match — take max count in the returned window
            counts = [float(rec.counts) for rec in records]
            logger.debug(
                f"hic_contacts: no exact bin match for {reg1}↔{reg2}; "
                f"using max of {len(counts)} records"
            )
            return max(counts)

        logger.warning(f"hic_contacts: no contact data for {r1} ↔ {r2}")
        return _NEUTRAL_CONTACT

    def _call_straw(
        self, url: str, norm: str, reg1: str, reg2: str, resolution: int
    ) -> list:
        """Thin hicstraw.straw wrapper — isolated here so tests can patch it.

        Args:
            url: .hic file URL.
            norm: Normalisation type (``"KR"`` or ``"NONE"``).
            reg1: Region string ``"{chrom}:{start}:{end}"`` (no chr prefix).
            reg2: Region string for the second locus.
            resolution: Bin size in bp.

        Returns:
            List of straw Record objects (``binX``, ``binY``, ``counts``).

        Raises:
            RuntimeError: If hicstraw is not installed.
        """
        try:
            import hicstraw
        except ImportError as exc:
            raise RuntimeError(
                "hicstraw is not installed; install hic-straw to use Hi-C contacts"
            ) from exc
        return hicstraw.straw("observed", norm, url, reg1, reg2, "BP", resolution)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _load_cell_lines(yaml_path: Path) -> dict:
        """Parse cell_lines.yaml.

        Args:
            yaml_path: Path to YAML file.

        Returns:
            ``{cell_line: {key: value, ...}, ...}``
        """
        if not yaml_path.exists():
            logger.warning(f"hic_contacts: cell_lines.yaml not found at {yaml_path}")
            return {}
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
