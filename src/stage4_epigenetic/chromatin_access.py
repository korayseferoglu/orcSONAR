"""ATAC-seq chromatin accessibility reader for Stage 4.

Reads open-chromatin signal from ENCODE ATAC-seq BigWig tracks.
Higher signal → more accessible chromatin → saRNA is more likely to engage
the target region, amplifying both on-target activity and off-target risk.

BigWig signal convention: RPKM (reads per kilobase per million).
Neutral value 0.0 is returned when the URL is not configured or the read
fails; the Stage 7 scoring engine normalises raw signals to [0, 1].
"""

from __future__ import annotations

from src.core.models import GenomicRegion
from src.stage4_epigenetic.encode_reader import UNKNOWN_SIGNAL, EncodeSignalReader

_ATAC_SIGNAL_TYPE: str = "atac_seq"


class ATACSeqReader(EncodeSignalReader):
    """Reads ATAC-seq open-chromatin signal from cell-line-specific ENCODE tracks.

    Inherits URL resolution, BigWig streaming, and SQLite caching from
    ``EncodeSignalReader``.

    Args:
        config: Pipeline configuration.
        cell_lines_yaml: Path to cell_lines.yaml (default: ``config/cell_lines.yaml``).
    """

    def get_accessibility(
        self, region: GenomicRegion, cell_line: str
    ) -> float:
        """Return mean ATAC-seq signal for a single genomic region.

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Mean RPKM signal, or 0.0 if the URL is not configured or the
            read fails.
        """
        url = self._get_url_for_cell_line(cell_line, _ATAC_SIGNAL_TYPE)
        if url is None:
            return UNKNOWN_SIGNAL
        return self.read_signal(url, region)

    def get_accessibility_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[float]:
        """Return mean ATAC-seq signal for multiple regions (single BigWig open).

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            Signal values in the same order as ``regions``.  Returns all 0.0
            if the URL is not configured.
        """
        url = self._get_url_for_cell_line(cell_line, _ATAC_SIGNAL_TYPE)
        if url is None:
            return [UNKNOWN_SIGNAL] * len(regions)
        return self.read_signal_bulk(url, regions)
