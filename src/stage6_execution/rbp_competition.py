"""RBP competition analysis for Stage 6 (hnRNPA1 eCLIP).

RBP (RNA-binding protein) occupancy at an off-target region COMPETES with saRNA
for binding to the target mRNA.  High hnRNPA1 eCLIP signal → the site is already
occupied by RBP → saRNA access is blocked → off-target risk DECREASES.

BigWig signal: fold-change over size-matched input (ENCODE eCLIP standard).
Competition score [0, 1] is derived via a saturating linear transform:
  competition_score = min(1.0, raw_signal / _RBP_SATURATION)

A region is considered "competing" when competition_score > _COMPETITION_THRESHOLD.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, RBPResult
from src.stage4_epigenetic.encode_reader import _NEUTRAL_SIGNAL, EncodeSignalReader

_HNRNPA1_SIGNAL_KEY: str = "hnrnpa1_eclip"
_RBP_SATURATION: float = 20.0        # FC ≥ 20 → competition score clamped to 1.0
_COMPETITION_THRESHOLD: float = 0.3  # score > 0.3 → is_competing = True
_DEFAULT_RBP_NAME: str = "hnRNPA1"


class RBPCompetitionReader(EncodeSignalReader):
    """Reads hnRNPA1 eCLIP signal from cell-line-specific ENCODE BigWig tracks.

    hnRNPA1 (heterogeneous nuclear ribonucleoprotein A1) is an abundant RBP
    that competes with RISC and short RNA duplexes for target site access.
    High occupancy at an off-target locus → saRNA is less likely to engage →
    off-target risk decreases.

    Args:
        config: Pipeline configuration.
        cell_lines_yaml: Path to cell_lines.yaml (default: ``config/cell_lines.yaml``).
    """

    def get_rbp_signal(self, region: GenomicRegion, cell_line: str) -> float:
        """Return raw mean hnRNPA1 eCLIP fold-change for one region.

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean fold-change over control, or 0.0 if not configured or on failure.
        """
        url = self._get_url_for_cell_line(cell_line, _HNRNPA1_SIGNAL_KEY)
        if url is None:
            return _NEUTRAL_SIGNAL
        return self.read_signal(url, region)

    def get_rbp_signal_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float]:
        """Batch hnRNPA1 eCLIP signal read with a single BigWig open.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            Signal values in the same order as ``regions``.
        """
        url = self._get_url_for_cell_line(cell_line, _HNRNPA1_SIGNAL_KEY)
        if url is None:
            return [_NEUTRAL_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)


def _competition_score(raw_signal: float) -> float:
    """Normalise raw hnRNPA1 fold-change to [0, 1] competition score.

    Args:
        raw_signal: Raw fold-change value from eCLIP BigWig.

    Returns:
        Competition score clamped to [0, 1].
    """
    if raw_signal <= 0.0:
        return 0.0
    return min(1.0, raw_signal / _RBP_SATURATION)


def assess_rbp_competition(
    regions: list[GenomicRegion],
    cell_line: str,
    config: OrcSonarConfig,
    cell_lines_yaml: str | Path = "config/cell_lines.yaml",
    rbp_name: str = _DEFAULT_RBP_NAME,
) -> list[RBPResult]:
    """Assess hnRNPA1 RBP competition at off-target genomic regions.

    For each region, reads hnRNPA1 eCLIP fold-change and converts it to a
    competition score [0, 1].  Higher score → site is more occluded by RBP →
    saRNA is less likely to access the region → off-target risk decreases.

    Args:
        regions: Off-target genomic intervals (chr-prefixed, hg38).
        cell_line: Cell line name, e.g. ``"HeLa"``.
        config: Pipeline configuration (provides cache DB path).
        cell_lines_yaml: Path to cell_lines.yaml.
        rbp_name: Name of the RBP assessed (informational; defaults to ``"hnRNPA1"``).

    Returns:
        One ``RBPResult`` per input region, in the same order.
    """
    if not regions:
        return []

    reader = RBPCompetitionReader(config, cell_lines_yaml=cell_lines_yaml)
    raw_signals = reader.get_rbp_signal_bulk(regions, cell_line)

    results: list[RBPResult] = []
    for region, raw in zip(regions, raw_signals, strict=True):
        score = _competition_score(raw)
        results.append(
            RBPResult(
                region=region,
                cell_line=cell_line,
                rbp_name=rbp_name,
                raw_signal=raw,
                competition_score=score,
                is_competing=score > _COMPETITION_THRESHOLD,
            )
        )
        logger.debug(
            f"rbp_competition: {region} cell={cell_line} rbp={rbp_name} "
            f"raw={raw:.3f} score={score:.3f}"
        )

    return results
