"""GRO-seq active transcription reader for Stage 4.

Reads plus-strand and minus-strand GRO-seq (or PRO-seq) signal from remote
BigWig tracks hosted on GEO / SRA.

Transcription semantics:
  Strong combined signal (plus + minus) in an off-target region indicates
  active transcription → the gene is expressed → saRNA has an elevated chance
  of engaging the region → risk increases.

  Strand-specific reads let callers distinguish:
    - Convergent transcription (both strands active) — typical of enhancers
    - Unidirectional transcription — typical coding or lncRNA genes

Return value convention:
  - Raw BigWig signal (RPM / RPKM depending on the track).
  - 0.0 (neutral) per strand when the URL is absent or on any read failure.
  - combined_signal = plus_signal + minus_signal.
  - Stage 7 normalises all signals to [0, 1].

YAML keys used (in cell_lines.yaml):
  gro_seq_plus_url  — plus-strand BigWig URL
  gro_seq_minus_url — minus-strand BigWig URL (negative values expected for
                       minus-strand BigWigs; reader takes the absolute value)
"""

from __future__ import annotations

from src.core.config import OrcSonarConfig
from src.core.models import GenomicRegion, GROseqResult
from src.stage4_epigenetic.encode_reader import EncodeSignalReader, _NEUTRAL_SIGNAL

_GROSEQ_PLUS_KEY: str = "gro_seq_plus_url"
_GROSEQ_MINUS_KEY: str = "gro_seq_minus_url"


class GROseqReader(EncodeSignalReader):
    """Reads GRO-seq / PRO-seq transcription signal from remote BigWig files.

    Inherits URL resolution, BigWig streaming, and SQLite caching from
    ``EncodeSignalReader``.  Reads plus and minus strands independently.

    Args:
        config: Pipeline configuration.
        cell_lines_yaml: Path to cell_lines.yaml (default:
            ``config/cell_lines.yaml``).
    """

    def get_transcription(
        self, region: GenomicRegion, cell_line: str
    ) -> GROseqResult:
        """Return GRO-seq signal for both strands at a genomic region.

        Args:
            region: Genomic interval (chr-prefixed, hg38).
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            GROseqResult with ``plus_signal``, ``minus_signal``, and
            ``combined_signal`` (sum).  Any absent or failed strand
            contributes 0.0.
        """
        plus_url = self._get_url_for_cell_line(cell_line, _GROSEQ_PLUS_KEY)
        minus_url = self._get_url_for_cell_line(cell_line, _GROSEQ_MINUS_KEY)

        plus_signal = (
            self.read_signal(plus_url, region) if plus_url else _NEUTRAL_SIGNAL
        )
        minus_signal = (
            abs(self.read_signal(minus_url, region)) if minus_url else _NEUTRAL_SIGNAL
        )

        return GROseqResult(
            region=region,
            plus_signal=plus_signal,
            minus_signal=minus_signal,
            combined_signal=plus_signal + minus_signal,
        )

    def get_transcription_bulk(
        self, regions: list[GenomicRegion], cell_line: str
    ) -> list[GROseqResult]:
        """Batch GRO-seq read — opens each strand BigWig once.

        Args:
            regions: Genomic intervals (chr-prefixed, hg38).
            cell_line: Cell line name.

        Returns:
            GROseqResult list in the same order as ``regions``.
        """
        if not regions:
            return []

        plus_url = self._get_url_for_cell_line(cell_line, _GROSEQ_PLUS_KEY)
        minus_url = self._get_url_for_cell_line(cell_line, _GROSEQ_MINUS_KEY)

        plus_signals = (
            self.read_signal_bulk(plus_url, regions)
            if plus_url
            else [_NEUTRAL_SIGNAL] * len(regions)
        )
        minus_signals = (
            [abs(v) for v in self.read_signal_bulk(minus_url, regions)]
            if minus_url
            else [_NEUTRAL_SIGNAL] * len(regions)
        )

        return [
            GROseqResult(
                region=region,
                plus_signal=p,
                minus_signal=m,
                combined_signal=p + m,
            )
            for region, p, m in zip(regions, plus_signals, minus_signals)
        ]
