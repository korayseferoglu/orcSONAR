"""Ago2 eCLIP loading assessment for Stage 6.

Ago2 (Argonaute 2) eCLIP signal indicates active RISC loading at a locus.
High Ago2 signal at an off-target region → that region is already engaged by
RISC → saRNA can be incorporated and produce off-target silencing → HIGHER risk.

BigWig signal: fold-change over size-matched input (ENCODE eCLIP standard).
Loading score [0, 1] is derived via a saturating linear transform:
  loading_score = min(1.0, raw_signal / _AGO2_SATURATION)

A region is considered "loaded" when loading_score > _LOADING_THRESHOLD.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.models import Ago2Result, GenomicRegion
from src.stage4_epigenetic.encode_reader import UNKNOWN_SIGNAL, EncodeSignalReader

_AGO2_SIGNAL_KEY: str = "ago2_eclip"
_AGO2_SATURATION: float = 20.0   # FC ≥ 20 → loading score clamped to 1.0
_LOADING_THRESHOLD: float = 0.3  # score > 0.3 → is_loaded = True


class Ago2Reader(EncodeSignalReader):
    """Reads Ago2 eCLIP signal from cell-line-specific ENCODE BigWig tracks.

    Ago2 eCLIP quantifies active RISC loading. A high fold-change over control
    at an off-target locus indicates the region is already RISC-engaged and
    therefore susceptible to saRNA-mediated silencing.

    Args:
        config: Pipeline configuration.
        cell_lines_yaml: Path to cell_lines.yaml (default: ``config/cell_lines.yaml``).
    """

    def get_ago2_signal(self, region: GenomicRegion, cell_line: str) -> float | None:
        """Return raw mean Ago2 eCLIP fold-change for one region.

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean fold-change over control, or 0.0 if not configured or on failure.
        """
        url = self._get_url_for_cell_line(cell_line, _AGO2_SIGNAL_KEY)
        if url is None:
            return UNKNOWN_SIGNAL
        return self.read_signal(url, region)

    def get_ago2_signal_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float | None]:
        """Batch Ago2 eCLIP signal read with a single BigWig open.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            Signal values in the same order as ``regions``; ``None`` where
            nothing could be measured (roadmap B2).
        """
        url = self._get_url_for_cell_line(cell_line, _AGO2_SIGNAL_KEY)
        if url is None:
            return [UNKNOWN_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)



def _fmt(value: float | None) -> str:
    """Format a possibly-unknown signal for a log line (roadmap B2)."""
    return "ÖLÇÜLMEDİ" if value is None else f"{value:.3f}"
def _loading_score(raw_signal: float | None) -> float | None:
    """Normalise raw Ago2 fold-change to [0, 1] loading score.

    Args:
        raw_signal: Raw fold-change value from eCLIP BigWig, or ``None``
            if nothing was measured there.

    Returns:
        Loading score in [0, 1], or ``None`` when the signal was not measured.
    """
    # An unmeasured signal is not a zero. Zero here means "no eCLIP signal",
    # which lowers the risk this channel contributes; returning it for a failed
    # read is how a dead source produced a safe-looking site (roadmap B2).
    if raw_signal is None:
        return None
    if raw_signal <= 0.0:
        return 0.0
    return min(1.0, raw_signal / _AGO2_SATURATION)


def assess_ago2_loading(
    regions: list[GenomicRegion],
    cell_line: str,
    config: OrcSonarConfig,
    cell_lines_yaml: str | Path = "config/cell_lines.yaml",
) -> list[Ago2Result]:
    """Assess Ago2 RISC loading at off-target genomic regions.

    For each region, reads Ago2 eCLIP fold-change and converts it to a
    loading score [0, 1].  Higher score → region is actively RISC-loaded →
    saRNA off-target silencing risk increases.

    Args:
        regions: Off-target genomic intervals (chr-prefixed, hg38).
        cell_line: Cell line name, e.g. ``"HeLa"``.
        config: Pipeline configuration (provides cache DB path).
        cell_lines_yaml: Path to cell_lines.yaml.

    Returns:
        One ``Ago2Result`` per input region, in the same order.
    """
    if not regions:
        return []

    reader = Ago2Reader(config, cell_lines_yaml=cell_lines_yaml)
    raw_signals = reader.get_ago2_signal_bulk(regions, cell_line)

    results: list[Ago2Result] = []
    for region, raw in zip(regions, raw_signals, strict=True):
        score = _loading_score(raw)
        results.append(
            Ago2Result(
                region=region,
                cell_line=cell_line,
                raw_signal=raw,
                loading_score=score,
                is_loaded=None if score is None else score > _LOADING_THRESHOLD,
            )
        )
        logger.debug(
            f"ago2_loading: {region} cell={cell_line} "
            f"raw={_fmt(raw)} score={_fmt(score)}"
        )

    return results
