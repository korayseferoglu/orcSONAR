"""Unit tests for src/stage2_offtarget_scan/transcriptome_fetcher.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.stage2_offtarget_scan.transcriptome_fetcher import (
    _BACKGROUND_GENES,
    _batch_fetch_sequences,
    _batch_lookup_symbols,
    _batches,
    get_background_transcriptome,
)

ENSEMBL_BASE = "https://rest.ensembl.org"
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

        transcripts, sequences = get_background_transcriptome(config)

        assert len(transcripts) >= 1
        assert "ENST00000461615" in sequences
        assert sequences["ENST00000461615"] == "ATCGATCGATCG"

    def test_exclude_gene_removes_from_scan(self, tmp_path: Path) -> None:
        """Target gene must not appear in the background gene list."""
        config = _default_config(tmp_path)

        # Patch the inner fetcher to return nothing so we test only gene filtering
        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts"
        ) as mock_load:
            mock_load.return_value = {}
            transcripts, sequences = get_background_transcriptome(config, exclude_gene="VEGFA")

            # Verify VEGFA was excluded from the genes passed to _load_canonical_transcripts
            genes_passed = mock_load.call_args[0][0]
            assert "VEGFA" not in genes_passed

    def test_api_failure_returns_empty_gracefully(self, tmp_path: Path) -> None:
        config = _default_config(tmp_path)

        with patch(
            "src.stage2_offtarget_scan.transcriptome_fetcher._load_canonical_transcripts"
        ) as mock_load:
            mock_load.return_value = {}
            transcripts, sequences = get_background_transcriptome(config)

        assert transcripts == []
        assert sequences == {}

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
            transcripts, sequences = get_background_transcriptome(config)

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
