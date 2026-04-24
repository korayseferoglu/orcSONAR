"""Histone modification ChIP-seq signal reader for Stage 4.

Reads H3K4me3, H3K27ac, and H3K27me3 signal from ENCODE ChIP-seq BigWig
tracks.  Signal semantics:

  H3K4me3  — active promoter mark.  High signal near off-target TSS increases
              the probability that the region is transcriptionally active and
              accessible to saRNA → higher risk.

  H3K27ac  — active enhancer / promoter mark.  High signal increases off-target
              engagement risk similar to H3K4me3.

  H3K27me3 — repressive (Polycomb) mark.  High signal indicates
              transcriptionally silenced chromatin → saRNA is *less* likely to
              engage → lower off-target risk.  Callers must invert this score.

BigWig signal convention: fold-enrichment over input (ChIP-seq standard).
Returns 0.0 (neutral) when the URL is absent or on any read failure.
"""

from __future__ import annotations

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion
from src.stage4_epigenetic.encode_reader import EncodeSignalReader, _NEUTRAL_SIGNAL

_H3K4ME3_KEY: str = "h3k4me3_chip"
_H3K27AC_KEY: str = "h3k27ac_chip"
_H3K27ME3_KEY: str = "h3k27me3_chip"


class HistoneMarkReader(EncodeSignalReader):
    """Reads H3K4me3, H3K27ac, and H3K27me3 ChIP-seq signal from ENCODE BigWig tracks.

    Inherits URL resolution, BigWig streaming, and SQLite caching from
    ``EncodeSignalReader``.

    Args:
        config: Pipeline configuration.
        cell_lines_yaml: Path to cell_lines.yaml (default: ``config/cell_lines.yaml``).
    """

    def get_h3k4me3(self, region: GenomicRegion, cell_line: str) -> float:
        """Return mean H3K4me3 signal for a region (active promoter mark).

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean fold-enrichment, or 0.0 if not configured or on failure.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K4ME3_KEY)
        if url is None:
            return _NEUTRAL_SIGNAL
        return self.read_signal(url, region)

    def get_h3k27ac(self, region: GenomicRegion, cell_line: str) -> float:
        """Return mean H3K27ac signal for a region (active enhancer/promoter mark).

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean fold-enrichment, or 0.0 if not configured or on failure.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K27AC_KEY)
        if url is None:
            return _NEUTRAL_SIGNAL
        return self.read_signal(url, region)

    def get_h3k27me3(self, region: GenomicRegion, cell_line: str) -> float:
        """Return mean H3K27me3 signal for a region (repressive Polycomb mark).

        A high value indicates silenced chromatin; callers should invert this
        when computing risk (high H3K27me3 → lower off-target engagement risk).

        Returns 0.0 when ``h3k27me3_chip`` is not configured for the cell line —
        meaning the repressive state is unknown (neutral, not assumed absent).

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean fold-enrichment, or 0.0 if not configured or on failure.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K27ME3_KEY)
        if url is None:
            return _NEUTRAL_SIGNAL
        return self.read_signal(url, region)

    def get_h3k4me3_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float]:
        """Batch H3K4me3 signal read with a single BigWig open.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            Signal values in the same order as ``regions``.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K4ME3_KEY)
        if url is None:
            return [_NEUTRAL_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)

    def get_h3k27ac_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float]:
        """Batch H3K27ac signal read with a single BigWig open.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            Signal values in the same order as ``regions``.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K27AC_KEY)
        if url is None:
            return [_NEUTRAL_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)

    def get_h3k27me3_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float]:
        """Batch H3K27me3 signal read with a single BigWig open.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            Signal values in the same order as ``regions``.
        """
        url = self._get_url_for_cell_line(cell_line, _H3K27ME3_KEY)
        if url is None:
            return [_NEUTRAL_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)
