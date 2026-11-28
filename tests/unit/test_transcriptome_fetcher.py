"""Unit tests for src/stage2_offtarget_scan/transcriptome_fetcher.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp_mock
from loguru import logger

from src.core.config import OrcSonarConfig
from src.core.exceptions import DataSourceError
from src.stage2_offtarget_scan.transcriptome_fetcher import (
    _BACKGROUND_GENES,
    _batch_fetch_sequences,
    _batch_lookup_symbols,
    _batches,
    get_background_transcriptome,
)

# Pinned host comes from the config default (B17); see test_transcript_resolver.
ENSEMBL_BASE = OrcSonarConfig.model_fields["ensembl_base_url"].default
LOOKUP_URL = f"{ENSEMBL_BASE}/lookup/symbol/homo_sapiens"
SEQ_URL = f"{ENSEMBL_BASE}/sequence/id"


def _default_config(tmp_path: Path) -> OrcSonarConfig:
    return OrcSonarConfig(
        target_gene="VEGFA",
        data_paths={"cache_db": str(tmp_path / "test_cache.db")},
    )


# ---------------------------------------------------------------------------
# _batches
# ---------------------------------------------------------------------------


class TestBatches:
    def test_exact_multiple(self) -> None:
        result = list(_batches([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_remainder(self) -> None:
        result = list(_batches([1, 2, 3], 2))
        assert result == [[1, 2], [3]]

    def test_empty(self) -> None:
        assert list(_batches([], 10)) == []

    def test_larger_than_list(self) -> None:
        assert list(_batches([1, 2], 10)) == [[1, 2]]


# ---------------------------------------------------------------------------
# _batch_lookup_symbols
# ---------------------------------------------------------------------------


class TestBatchLookupSymbols:
    @resp_mock.activate
    def test_returns_canonical_transcript(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "ACTB": {
                    "id": "ENSG00000075624",
                    "seq_region_name": "7",
                    "start": 5527148,
                    "end": 5530601,
                    "strand": 1,
                    "Transcript": [
                        {
                            "id": "ENST00000461615",
                            "is_canonical": 1,
                            "start": 5527148,
                            "end": 5530601,
                            "strand": 1,
                        }
                    ],
                }
            },
            status=200,
        )

        result = _batch_lookup_symbols(["ACTB"], config)

        assert "ACTB" in result
        t = result["ACTB"]
        assert t.transcript_id == "ENST00000461615"
        assert t.gene == "ACTB"
        assert t.chrom == "chr7"
        assert t.is_canonical is True
        assert t.strand == "+"

    @resp_mock.activate
    def test_minus_strand(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "TP53": {
                    "id": "ENSG00000141510",
                    "seq_region_name": "17",
                    "start": 7661779,
                    "end": 7687538,
                    "strand": -1,
                    "Transcript": [
                        {
                            "id": "ENST00000269305",
                            "is_canonical": 1,
                            "start": 7661779,
                            "end": 7687538,
                            "strand": -1,
                        }
                    ],
                }
            },
            status=200,
        )

        result = _batch_lookup_symbols(["TP53"], config)
        assert result["TP53"].strand == "-"

    @resp_mock.activate
    def test_fallback_to_first_when_no_canonical_flag(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "GAPDH": {
                    "id": "ENSG00000111640",
                    "seq_region_name": "12",
                    "start": 6534517,
                    "end": 6538371,
                    "strand": 1,
                    "Transcript": [
                        {"id": "ENST00000229239", "start": 6534517, "end": 6538371, "strand": 1},
                        {"id": "ENST00000396859", "start": 6534517, "end": 6538000, "strand": 1},
                    ],
                }
            },
            status=200,
        )

        result = _batch_lookup_symbols(["GAPDH"], config)
        # Should pick first transcript in absence of is_canonical flag
        assert result["GAPDH"].transcript_id == "ENST00000229239"

    @resp_mock.activate
    def test_api_failure_returns_empty(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            status=500,
        )

        result = _batch_lookup_symbols(["ACTB"], config)
        assert result == {}

    @resp_mock.activate
    def test_chrom_prefix_not_doubled(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "MYC": {
                    "id": "ENSG00000136997",
                    "seq_region_name": "chr8",  # already has prefix
                    "start": 127735434,
                    "end": 127742951,
                    "strand": 1,
                    "Transcript": [
                        {"id": "ENST00000377970", "is_canonical": 1,
                         "start": 127735434, "end": 127742951, "strand": 1}
                    ],
                }
            },
            status=200,
        )

        result = _batch_lookup_symbols(["MYC"], config)
        assert result["MYC"].chrom == "chr8"


# ---------------------------------------------------------------------------
# _batch_fetch_sequences
# ---------------------------------------------------------------------------


class TestBatchFetchSequences:
    @resp_mock.activate
    def test_returns_sequence(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            SEQ_URL,
            json=[{"id": "ENST00000461615", "seq": "ATCGATCG"}],
            status=200,
        )

        result = _batch_fetch_sequences(["ENST00000461615"], config)
        assert result["ENST00000461615"] == "ATCGATCG"

    @resp_mock.activate
    def test_sequence_uppercased(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            SEQ_URL,
            json=[{"id": "ENST00000461615", "seq": "atcgatcg"}],
            status=200,
        )

        result = _batch_fetch_sequences(["ENST00000461615"], config)
        assert result["ENST00000461615"] == "ATCGATCG"

    @resp_mock.activate
    def test_api_failure_returns_empty(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(resp_mock.POST, SEQ_URL, status=503)

        result = _batch_fetch_sequences(["ENST00000461615"], config)
        assert result == {}

    @resp_mock.activate
    def test_multiple_ids_in_one_batch(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        resp_mock.add(
            resp_mock.POST,
            SEQ_URL,
            json=[
                {"id": "ENST00000000001", "seq": "AAAA"},
                {"id": "ENST00000000002", "seq": "CCCC"},
            ],
            status=200,
        )

        result = _batch_fetch_sequences(["ENST00000000001", "ENST00000000002"], config)
        assert len(result) == 2
        assert result["ENST00000000001"] == "AAAA"
        assert result["ENST00000000002"] == "CCCC"


# ---------------------------------------------------------------------------
# get_background_transcriptome — integration-style with mocks
# ---------------------------------------------------------------------------


class TestGetBackgroundTranscriptome:
    @resp_mock.activate
    def test_returns_transcripts_and_sequences(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        # Mock symbol lookup (return one gene)
        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "ACTB": {
                    "id": "ENSG00000075624",
                    "seq_region_name": "7",
                    "start": 5527148,
                    "end": 5530601,
                    "strand": 1,
                    "Transcript": [
                        {
                            "id": "ENST00000461615",
                            "is_canonical": 1,
                            "start": 5527148,
                            "end": 5530601,
                            "strand": 1,
                        }
                    ],
                }
            },
            status=200,
        )

        # Repeat the mock for every batch (there are many batches for the full gene list)
        for _ in range(50):
            resp_mock.add(
                resp_mock.POST,
                LOOKUP_URL,
                json={},
                status=200,
            )

        # Mock sequence fetch
        for _ in range(50):
            resp_mock.add(
                resp_mock.POST,
                SEQ_URL,
                json=[{"id": "ENST00000461615", "seq": "ATCGATCGATCG"}],
                status=200,
            )

        transcripts, sequences, _coverage = get_background_transcriptome(config)

        assert len(transcripts) >= 1
        assert "ENST00000461615" in sequences
        assert sequences["ENST00000461615"] == "ATCGATCGATCG"

    def test_exclude_gene_removes_from_scan(self, tmp_path: Path) -> None:
        """Target gene must not appear in the background gene list."""
        config = _default_config(tmp_path)

        # One resolved transcript, so the call reaches the end: an empty result
        # now raises (Bulgu 12), and this test is about gene filtering, not the
        # outage guard — it must not depend on that guard either way.
        from src.core.models import TranscriptInfo

        t_info = TranscriptInfo(
            transcript_id="ENST00000000001",
            gene="TESTGENE",
            chrom="chr1",
            start=0,
            end=100,
            strand="+",
            source="Ensembl",
        )
        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts",
            return_value={"TESTGENE": t_info},
        ) as mock_load, patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_sequences",
            return_value={"ENST00000000001": "ATCGATCG"},
        ):
            get_background_transcriptome(config, exclude_gene="VEGFA")

            # Verify VEGFA was excluded from the genes passed to _load_canonical_transcripts
            genes_passed = mock_load.call_args[0][0]
            assert "VEGFA" not in genes_passed

    def test_total_resolution_failure_raises_rather_than_returning_empty(
        self, tmp_path: Path
    ) -> None:
        """Losing every background gene is an outage, not a measurement.

        This test replaces ``test_api_failure_returns_empty_gracefully``, which
        asserted the opposite and so defended the bug (audit 2026-11-19,
        Bulgu 12). Returning ``[]`` here made the whole search space vanish:
        ``seed_aligner`` then scanned the target gene alone, found zero
        off-target sites, and the run reported ``risk=SAFE (0.0000)`` with
        exit 0 — a failed data source producing the safest possible answer,
        which is the direction invariant 2 exists to forbid.
        """
        config = _default_config(tmp_path)

        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts"
        ) as mock_load:
            mock_load.return_value = {}
            with pytest.raises(DataSourceError, match="no canonical transcripts"):
                get_background_transcriptome(config)

    def test_partial_resolution_is_a_measurement_and_passes_through(
        self, tmp_path: Path
    ) -> None:
        """Some genes resolving is real data; only *total* loss is an outage.

        The guard must not turn an ordinary partial result into a failure —
        that would make the pipeline unrunnable whenever one symbol is retired.
        """
        from src.core.models import TranscriptInfo

        config = _default_config(tmp_path)
        t_info = TranscriptInfo(
            transcript_id="ENST00000000001",
            gene="TESTGENE",
            chrom="chr1",
            start=0,
            end=100,
            strand="+",
            source="Ensembl",
        )

        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts",
            return_value={"TESTGENE": t_info},
        ), patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_sequences",
            return_value={"ENST00000000001": "ATCGATCG"},
        ):
            transcripts, _, _coverage = get_background_transcriptome(config)

        assert len(transcripts) == 1

    def test_sequences_normalised_to_rna_u(self, tmp_path: Path) -> None:
        """get_background_transcriptome itself returns T-alphabet; caller normalises."""
        from src.core.models import TranscriptInfo

        config = _default_config(tmp_path)
        t_info = TranscriptInfo(
            transcript_id="ENST00000000001",
            gene="TESTGENE",
            chrom="chr1",
            start=0,
            end=100,
            strand="+",
            source="Ensembl",
        )

        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts",
            return_value={"TESTGENE": t_info},
        ), patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_sequences",
            return_value={"ENST00000000001": "ATCGATCG"},
        ):
            transcripts, sequences, _coverage = get_background_transcriptome(config)

        assert len(transcripts) == 1
        assert sequences["ENST00000000001"] == "ATCGATCG"


# ---------------------------------------------------------------------------
# Background gene list sanity checks
# ---------------------------------------------------------------------------


class TestBackgroundGeneList:
    def test_minimum_size(self) -> None:
        assert len(_BACKGROUND_GENES) >= 100

    def test_no_duplicates(self) -> None:
        assert len(_BACKGROUND_GENES) == len(set(_BACKGROUND_GENES))

    def test_all_uppercase(self) -> None:
        for g in _BACKGROUND_GENES:
            assert g == g.upper(), f"{g!r} is not uppercase"

    def test_contains_key_biology_genes(self) -> None:
        must_have = {"AGO2", "DICER1", "TP53", "ACTB", "GAPDH", "MYC"}
        assert must_have.issubset(set(_BACKGROUND_GENES))


class TestBackgroundCoverageIsReported:
    """A run must say how much of its declared search space it actually got.

    Roadmap R12a. `R1` made a *total* loss of the background set an error, but
    a partial loss passes by design — and the 2026-11-19 run showed that is
    not enough: Ensembl answered two of three symbol batches with 504, 22 of
    182 genes resolved (12%), four sites were found instead of 41, and the
    report said SAFE (0.2909) without mentioning any of it.

    The background set is a *declared*, fixed list, so coverage is a known
    denominator. If it varies silently from run to run, no two runs are
    comparable, which is fatal for the cell-line-specificity claim.
    """

    def test_coverage_is_returned_alongside_the_transcripts(self, tmp_path: Path) -> None:
        from src.core.models import TranscriptInfo

        config = _default_config(tmp_path)
        t_info = TranscriptInfo(
            transcript_id="ENST00000000001", gene="TESTGENE", chrom="chr1",
            start=0, end=100, strand="+", source="Ensembl",
        )
        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts",
            return_value={"TESTGENE": t_info},
        ), patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_sequences",
            return_value={"ENST00000000001": "ATCGATCG"},
        ):
            _transcripts, _sequences, coverage = get_background_transcriptome(config)

        assert coverage["requested"] == 183, "the declared set is 183 genes"
        assert coverage["resolved"] == 1
        assert coverage["fraction"] == pytest.approx(1 / 183, abs=1e-6)

    def test_excluding_the_target_gene_shrinks_the_denominator(
        self, tmp_path: Path
    ) -> None:
        """Coverage must be reported against what was actually asked for."""
        from src.core.models import TranscriptInfo

        config = _default_config(tmp_path)
        t_info = TranscriptInfo(
            transcript_id="ENST00000000001", gene="ACTB", chrom="chr1",
            start=0, end=100, strand="+", source="Ensembl",
        )
        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts",
            return_value={"ACTB": t_info},
        ), patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_sequences",
            return_value={"ENST00000000001": "ATCGATCG"},
        ):
            *_, coverage = get_background_transcriptome(config, exclude_gene="ACTB")

        assert coverage["requested"] == 182


class TestLookupBatchSizeIsMeasured:
    """The batch size is a measured limit, not a guess.

    Measured against the live Ensembl REST API on 2026-11-24, POSTing
    /lookup/symbol/homo_sapiens with expand=1:

        batch=80  -> TimeoutError after 120s   (what the pipeline was doing)
        batch=40  -> OK in 70.4s               (uncomfortably close to the edge)
        batch=20  -> OK in 31.0s

    expand=1 cannot be dropped: `_batch_lookup_symbols` reads
    `gene_data["Transcript"]` to pick the canonical transcript, and without
    expand there is no transcript list. So the batch size is the only lever.
    """

    def test_batch_is_small_enough_to_complete(self) -> None:
        from src.stage2_offtarget_scan.transcriptome_fetcher import _LOOKUP_BATCH

        assert _LOOKUP_BATCH <= 20, (
            f"_LOOKUP_BATCH is {_LOOKUP_BATCH}; measured on 2026-11-24, an "
            "expand=1 lookup of 80 genes times out at 120s and 40 takes 70s. "
            "Two of three batches failing is how the 2026-11-19 run resolved "
            "only 12% of the background set."
        )


# ---------------------------------------------------------------------------
# Roadmap B10a — a null coordinate must not vanish, and must not flip a strand
# ---------------------------------------------------------------------------


class TestNullCoordinatesFromEnsembl:
    """A missing coordinate is unknown; it is not a reason to lose a gene.

    `_batch_lookup_symbols` built `TranscriptInfo` with
    ``canonical_raw.get("start", gene_data.get("start", 0))``. The default of
    the outer `get` is itself a `get`, so a response that carries the key with
    an explicit ``null`` — which Ensembl does emit — produced ``start=None``,
    which Pydantic rejected, which the surrounding ``except Exception`` logged
    at **debug** level. The gene then disappeared from the search space with no
    visible trace at INFO. mypy was reporting exactly this
    (``Argument "start" … has incompatible type "Any | None"``) and the error
    was lost inside `B10`'s backlog.

    Two consequences, and the second is worse:

    * the gene is dropped, and a smaller background reads as *fewer
      off-targets*, so the failure points toward SAFE (invariant 2);
    * the same construct on the line above governs **strand**
      (``canonical_raw.get("strand", gene_data.get("strand", 1))``). A null
      there is not ``1``, so the code assigned ``"-"`` — a silently wrong
      strand rather than a dropped gene, which is the class rule 10 exists for.

    At `D1`'s ~250k transcripts either one becomes mass silent loss, which is
    why `B10a` is scoped ahead of it.
    """

    @resp_mock.activate
    def test_a_null_start_does_not_silently_drop_the_gene(
        self, tmp_path: Path
    ) -> None:
        # loguru does not route through stdlib logging, so `caplog` sees
        # nothing. A sink added here is explicit about what level it collects,
        # which is the thing under test: the message used to be `debug`.
        collected: list[str] = []
        sink = logger.add(collected.append, level="WARNING")
        config = _default_config(tmp_path)
        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "ACTB": {
                    "id": "ENSG00000075624",
                    "seq_region_name": "7",
                    "start": None,
                    "end": 5530601,
                    "strand": 1,
                    "Transcript": [
                        {"id": "ENST00000461615", "is_canonical": 1,
                         "start": None, "end": 5530601, "strand": 1}
                    ],
                }
            },
            status=200,
        )

        try:
            result = _batch_lookup_symbols(["ACTB"], config)
        finally:
            logger.remove(sink)

        # Either the gene is kept with a usable coordinate, or it is refused
        # loudly. What it must not be is absent and quiet.
        if "ACTB" not in result:
            assert any("ACTB" in message for message in collected), (
                "the gene was dropped and nothing at WARNING or above said "
                "so — a smaller background reads as fewer off-targets "
                "(invariant 2)"
            )

    @resp_mock.activate
    def test_a_null_strand_is_not_silently_read_as_minus(
        self, tmp_path: Path
    ) -> None:
        """`None != 1`, so the old expression chose "-" without saying so."""
        config = _default_config(tmp_path)
        resp_mock.add(
            resp_mock.POST,
            LOOKUP_URL,
            json={
                "TP53": {
                    "id": "ENSG00000141510",
                    "seq_region_name": "17",
                    "start": 7668402,
                    "end": 7687550,
                    "strand": None,
                    "Transcript": [
                        {"id": "ENST00000269305", "is_canonical": 1,
                         "start": 7668402, "end": 7687550, "strand": None}
                    ],
                }
            },
            status=200,
        )

        result = _batch_lookup_symbols(["TP53"], config)

        if "TP53" in result:
            assert result["TP53"].strand == "+", (
                "a null strand was turned into '-' — an unknown became a "
                "definite, wrong orientation (rule 10)"
            )
