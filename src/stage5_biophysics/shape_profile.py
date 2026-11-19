"""SHAPE-Seq accessibility reader for Stage 5 (orcSONAR).

Two data layouts are supported:

1. **icSHAPE per-transcript** (e.g. ``GSM4333258_HeLa_icSHAPE.txt.gz`` from
   GEO GSE145805 — Sun L. et al., 2021). One row per Ensembl transcript:
       transcript_id  length  gene  r_1  r_2  ...  r_length
   ``r_i`` is a normalised reactivity in [0, 1] or the literal "NULL".
   Selected when the off-target site provides ``transcript_id`` + transcript-
   relative ``tx_start`` / ``tx_end`` and the matching ENST appears in the
   icSHAPE table (Ensembl version suffix is stripped on lookup).

2. **Legacy ``.shape`` / ``.map``** — two columns ``position\\treactivity``
   over a single coordinate space. Retained for hand-curated profiles and
   unit-test fixtures.

If neither path produces measured nucleotides, the result is the same
neutral fallback (``accessibility_score = 0.5``,
``single_stranded_fraction = 0.5``, ``data_available = False``).
"""

from __future__ import annotations

import array
import gzip
import math
import os
from functools import lru_cache

from loguru import logger

from src.core.models import GenomicRegion, ShapeResult

# Reactivity thresholds (Wilkinson et al. 2008)
_SINGLE_STRANDED_THRESHOLD: float = 0.7
_DOUBLE_STRANDED_THRESHOLD: float = 0.3

_NULL_TOKENS: frozenset[str] = frozenset(
    {"NULL", "null", "NA", "N/A", "nan", "NaN", ".", "-999", "-999.0"}
)


# ---------------------------------------------------------------------------
# Legacy .shape / .map loader (single coordinate space)
# ---------------------------------------------------------------------------


def _load_shape_data(cell_line: str, data_dir: str) -> dict[int, float] | None:
    """Load a legacy two-column SHAPE/.map profile for a cell line.

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
                    if val_str in _NULL_TOKENS:
                        continue
                    data[pos] = float(val_str)
                except (ValueError, IndexError):
                    continue
    except OSError as exc:
        logger.warning("Cannot read SHAPE file {}: {}", path, exc)
        return None

    logger.debug("Loaded {} SHAPE reactivities from {}", len(data), path)
    return data or None


# ---------------------------------------------------------------------------
# icSHAPE per-transcript loader (transcriptome-wide)
# ---------------------------------------------------------------------------


def _strip_ensembl_version(transcript_id: str) -> str:
    """Strip the trailing version suffix from an Ensembl ID (ENST.X → ENST)."""
    return transcript_id.split(".", 1)[0]


def _find_icshape_file(cell_line: str, data_dir: str) -> str | None:
    """Return the path to a ``*icSHAPE*.txt.gz`` file under data_dir/{cell_line}/.

    The match is case-insensitive on the cell-line directory name and on the
    "icSHAPE" substring. Returns ``None`` when no such file is present.
    """
    cell_dir = os.path.join(data_dir, cell_line)
    if not os.path.isdir(cell_dir):
        try:
            entries = os.listdir(data_dir)
        except OSError:
            return None
        for entry in entries:
            if entry.lower() == cell_line.lower():
                cell_dir = os.path.join(data_dir, entry)
                break
        else:
            return None

    try:
        candidates = sorted(os.listdir(cell_dir))
    except OSError:
        return None

    for fname in candidates:
        lower = fname.lower()
        if "icshape" in lower and lower.endswith(".txt.gz"):
            return os.path.join(cell_dir, fname)
    return None


@lru_cache(maxsize=8)
def _load_icshape_data(
    cell_line: str, data_dir: str
) -> dict[str, array.array[float]] | None:
    """Load a per-transcript icSHAPE table into memory (cached per process).

    File format (whitespace = TAB):
        transcript_id  length  gene_symbol  r_1  r_2  ...  r_length

    NULL / NA / -999 sentinels are converted to ``NaN``. Keys are stripped
    of Ensembl version suffixes so that lookups can be done with either form.
    Reactivities are stored as ``array.array('f')`` (4 bytes/float) to keep
    a transcriptome-wide table within ~500 MB of memory.

    Args:
        cell_line: Cell line name (e.g. "HeLa").
        data_dir:  SHAPE_Seq root directory.

    Returns:
        ``{ENST: array('f', [r_1, r_2, …])}`` mapping (NaN for NULL) or
        ``None`` when no icSHAPE file is found / file is unreadable.
    """
    path = _find_icshape_file(cell_line, data_dir)
    if path is None:
        return None

    table: dict[str, array.array[float]] = {}
    try:
        with gzip.open(path, mode="rt", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not line:
                    continue
                cols = line.split("\t")
                if len(cols) < 4:
                    continue
                tid = _strip_ensembl_version(cols[0].strip())
                try:
                    length = int(cols[1])
                except ValueError:
                    continue
                if length <= 0 or len(cols) < 3 + length:
                    continue
                # Reactivity values start at col index 3 and span `length` cols.
                values = cols[3 : 3 + length]
                buf = array.array("f")
                buf.extend(_parse_reactivity(v) for v in values)
                table[tid] = buf
    except OSError as exc:
        logger.warning("icSHAPE: cannot read {} ({})", path, exc)
        return None

    if not table:
        return None
    logger.info(
        "icSHAPE: loaded {} transcripts from {} (cell_line={})",
        len(table),
        os.path.basename(path),
        cell_line,
    )
    return table


def _parse_reactivity(token: str) -> float:
    """Parse one icSHAPE reactivity column; NULL-like tokens map to NaN."""
    t = token.strip()
    if not t or t in _NULL_TOKENS:
        return math.nan
    try:
        return float(t)
    except ValueError:
        return math.nan


def _accessibility_from_values(values: list[float]) -> tuple[float, float, float]:
    """Compute (mean_reactivity, accessibility_score, single_stranded_fraction).

    *values* is a list of measured reactivities (no NaN). The score is the
    mean reactivity clamped at 2.0 then mapped to [0, 1] by dividing by 2.
    The single-stranded fraction is the share of positions ≥ 0.7
    (Wilkinson et al. 2008 threshold).
    """
    n = len(values)
    mean_r = sum(values) / n
    accessibility = min(mean_r / 2.0, 1.0)
    ss_frac = sum(1 for r in values if r >= _SINGLE_STRANDED_THRESHOLD) / n
    return mean_r, accessibility, ss_frac


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_shape_accessibility(
    region: GenomicRegion,
    cell_line: str,
    data_dir: str,
    transcript_id: str | None = None,
    tx_start: int | None = None,
    tx_end: int | None = None,
) -> ShapeResult:
    """Compute SHAPE-derived accessibility for an off-target site.

    Strategy:
      1. If ``transcript_id`` + ``tx_start`` + ``tx_end`` are supplied AND a
         per-transcript icSHAPE file is available for this cell line AND the
         (versionless) transcript ID is present in that file, average the
         reactivities at transcript positions ``tx_start..tx_end-1``.
      2. Otherwise fall back to the legacy ``.shape`` / ``.map`` lookup keyed
         by the genomic region's ``start..end-1``.
      3. If neither produces measured nucleotides, return a neutral score
         (0.5) with ``data_available=False``.

    Args:
        region:        Genomic interval (kept verbatim in the result).
        cell_line:     Target cell line (e.g. "HeLa").
        data_dir:      SHAPE_Seq root directory.
        transcript_id: Ensembl transcript ID (with or without version) the
            off-target site belongs to. Required for icSHAPE lookup.
        tx_start:      0-based transcript-relative start of the off-target
            window (inclusive).
        tx_end:        0-based transcript-relative end of the off-target
            window (exclusive).

    Returns:
        ShapeResult with ``mean_reactivity``, ``accessibility_score``,
        ``single_stranded_fraction``, ``data_available``, and the input
        ``region``.
    """
    use_icshape = (
        transcript_id is not None
        and tx_start is not None
        and tx_end is not None
        and tx_end > tx_start >= 0
    )

    if use_icshape:
        table = _load_icshape_data(cell_line, data_dir)
        if table is not None:
            tid = _strip_ensembl_version(transcript_id)  # type: ignore[arg-type]
            reactivities = table.get(tid)
            if reactivities is not None:
                # Clamp window to transcript bounds; tx_end is exclusive.
                lo = max(0, tx_start)  # type: ignore[arg-type]
                hi = min(len(reactivities), tx_end)  # type: ignore[arg-type]
                window_vals = [
                    r for r in reactivities[lo:hi] if not math.isnan(r)
                ]
                if window_vals:
                    mean_r, access, ss = _accessibility_from_values(window_vals)
                    return ShapeResult(
                        region=region,
                        mean_reactivity=round(mean_r, 4),
                        accessibility_score=round(access, 4),
                        single_stranded_fraction=round(ss, 4),
                        data_available=True,
                    )
                # Transcript present but every measured slot in the window is
                # NULL — report the reactivity as UNKNOWN, with data_available=True so
                # downstream code knows icSHAPE *was* consulted.
                return ShapeResult(
                    region=region,
                    mean_reactivity=None,
                    accessibility_score=None,
                    single_stranded_fraction=None,
                    data_available=True,
                )
            logger.debug(
                "icSHAPE: transcript {} not in {} table — trying legacy fallback",
                transcript_id,
                cell_line,
            )

    raw = _load_shape_data(cell_line, data_dir)
    if raw is None:
        logger.debug(
            "SHAPE data unavailable for {} in {}; reactivity is unknown",
            cell_line,
            region,
        )
        return ShapeResult(
            region=region,
            mean_reactivity=None,
            accessibility_score=None,
            single_stranded_fraction=None,
            data_available=False,
        )

    region_reactivities: list[float] = []
    for pos_1based in range(region.start + 1, region.end + 1):
        if pos_1based in raw:
            region_reactivities.append(raw[pos_1based])

    if not region_reactivities:
        logger.debug(
            "No SHAPE positions overlap region {}; reactivity is unknown", region
        )
        return ShapeResult(
            region=region,
            mean_reactivity=None,
            accessibility_score=None,
            single_stranded_fraction=None,
            data_available=True,
        )

    mean_r, access, ss = _accessibility_from_values(region_reactivities)
    return ShapeResult(
        region=region,
        mean_reactivity=round(mean_r, 4),
        accessibility_score=round(access, 4),
        single_stranded_fraction=round(ss, 4),
        data_available=True,
    )
