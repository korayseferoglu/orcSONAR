"""SHAPE-Seq accessibility reader for Stage 5 (orcSONAR)."""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from src.core.models import GenomicRegion, ShapeResult

# Reactivity thresholds (Wilkinson et al. 2008)
_SINGLE_STRANDED_THRESHOLD: float = 0.7
_DOUBLE_STRANDED_THRESHOLD: float = 0.3


def _load_shape_data(cell_line: str, data_dir: str) -> Optional[dict[int, float]]:
    """Load SHAPE reactivity data for a cell line.

    Searches *data_dir*/{cell_line}/ for any .shape or .map file and
    parses it. Returns a dict mapping 1-based nucleotide position to
    reactivity, or None if no file is found.

    Args:
        cell_line: Cell line name (e.g. "HeLa"). Case-insensitive.
        data_dir:  Root SHAPE_Seq directory.

    Returns:
        Position → reactivity dict, or None when data are absent.
    """
    cell_dir = os.path.join(data_dir, cell_line)
    if not os.path.isdir(cell_dir):
        # Try case-insensitive match
        try:
            entries = os.listdir(data_dir)
        except OSError:
            return None
        for entry in entries:
            if entry.lower() == cell_line.lower():
                cell_dir = os.path.join(data_dir, entry)
                break
        else:
            logger.debug("SHAPE directory not found for cell line {}", cell_line)
            return None

    shape_files: list[str] = []
    try:
        for fname in os.listdir(cell_dir):
            if fname.endswith((".shape", ".map")):
                shape_files.append(os.path.join(cell_dir, fname))
    except OSError:
        return None

    if not shape_files:
        logger.debug("No .shape/.map files found in {}", cell_dir)
        return None

    # Use the first file found (convention: one file per cell line)
    path = sorted(shape_files)[0]
    data: dict[int, float] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    pos = int(parts[0])
                    val_str = parts[1]
                    if val_str in ("-999", "-999.0", "nan", "N/A", "."):
                        # Sentinel for unmeasured positions
                        continue
                    data[pos] = float(val_str)
                except (ValueError, IndexError):
                    continue
    except OSError as exc:
        logger.warning("Cannot read SHAPE file {}: {}", path, exc)
        return None

    logger.debug("Loaded {} SHAPE reactivities from {}", len(data), path)
    return data or None


def get_shape_accessibility(
    region: GenomicRegion,
    cell_line: str,
    data_dir: str,
) -> ShapeResult:
    """Compute SHAPE-derived accessibility for a genomic region.

    Maps the region's span to a 0-based position range and looks up
    per-nucleotide reactivities. Positions with no data are excluded from
    the average. If no data are available, returns a neutral (0.5) score
    with ``data_available=False``.

    Args:
        region:    Genomic interval (hg38). ``region.start`` is 0-based.
        cell_line: One of the 8 supported cell lines.
        data_dir:  Path to the SHAPE_Seq root directory.

    Returns:
        ShapeResult with mean_reactivity, accessibility_score,
        single_stranded_fraction, and data_available.
    """
    raw = _load_shape_data(cell_line, data_dir)

    if raw is None:
        logger.info(
            "SHAPE data unavailable for {} in {}; using neutral score",
            cell_line,
            region,
        )
        return ShapeResult(
            region=region,
            mean_reactivity=0.0,
            accessibility_score=0.5,
            single_stranded_fraction=0.5,
            data_available=False,
        )

    # Collect reactivities for positions within the region (1-based in file)
    region_reactivities: list[float] = []
    for pos_1based in range(region.start + 1, region.end + 1):
        if pos_1based in raw:
            region_reactivities.append(raw[pos_1based])

    if not region_reactivities:
        logger.debug(
            "No SHAPE positions overlap region {}; returning neutral score", region
        )
        return ShapeResult(
            region=region,
            mean_reactivity=0.0,
            accessibility_score=0.5,
            single_stranded_fraction=0.5,
            data_available=True,
        )

    mean_react = sum(region_reactivities) / len(region_reactivities)
    ss_frac = sum(
        1 for r in region_reactivities if r >= _SINGLE_STRANDED_THRESHOLD
    ) / len(region_reactivities)

    # Normalise reactivity to [0, 1]: clamp at 2.0 (typical upper bound)
    accessibility = min(mean_react / 2.0, 1.0)

    return ShapeResult(
        region=region,
        mean_reactivity=round(mean_react, 4),
        accessibility_score=round(accessibility, 4),
        single_stranded_fraction=round(ss_frac, 4),
        data_available=True,
    )
