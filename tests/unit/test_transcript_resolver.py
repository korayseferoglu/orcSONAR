"""Unit tests for Stage 1 transcript isoform resolver."""

from __future__ import annotations

from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest
import responses as resp_mock

from src.core.config import OrcSonarConfig
from src.core.exceptions import DataSourceError
from src.stage1_genomic_map.transcript_resolver import (
    _ncbi_esearch_gene_id,
    get_transcript_sequence,
    resolve_transcripts,
)
from src.stage1_genomic_map.transcript_resolver import run as transcript_resolver_run

FIXTURES = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_config(tmp_path: Path) -> OrcSonarConfig:
    return OrcSonarConfig(
        data_paths={
            "epdnew_bed": str(FIXTURES / "sample_epdnew.bed"),
            "fantom5_bed": str(FIXTURES / "sample_fantom5.bed"),
            "cache_db": str(tmp_path / "test_cache.db"),
        }
    )


@pytest.fixture(autouse=True)
def no_sleep():
    """Skip all rate-limiting and tenacity retry waits in tests."""
    with mock.patch("time.sleep"), mock.patch("tenacity.nap.sleep"):
        yield


# ---------------------------------------------------------------------------
# Mock payloads
# ---------------------------------------------------------------------------

_ENSEMBL_VEGFA = {
    "id": "ENSG00000112715",
    "display_name": "VEGFA",
    "seq_region_name": "6",
    "start": 43770159,
    "end": 43786487,
    "strand": 1,
    "Transcript": [
        {
            "id": "ENST00000376218",
            "display_name": "VEGFA-201",
            "start": 43770159,
            "end": 43786487,
            "strand": 1,
            "is_canonical": 1,
            "biotype": "protein_coding",
        },
        {
            "id": "ENST00000511180",
            "display_name": "VEGFA-202",
            "start": 43770665,
            "end": 43786487,
            "strand": 1,
            "is_canonical": 0,
            "biotype": "processed_transcript",
        },
    ],
}

# No transcript carries is_canonical=1 — longest should be promoted
_ENSEMBL_NO_CANONICAL = {
    "seq_region_name": "1",
    "start": 100000,
    "end": 200000,
    "strand": 1,
    "Transcript": [
        # shorter: 150000 - 100000 = 50 000 bp
        {"id": "ENST00000001", "start": 100000, "end": 150000, "strand": 1},
        # longer:  200000 - 100000 = 100 000 bp  ← should become canonical
        {"id": "ENST00000002", "start": 100000, "end": 200000, "strand": 1},
    ],
}

_NCBI_ESEARCH = {
    "esearchresult": {"idlist": ["99999"], "count": "1", "retmax": "1", "retstart": "0"}
}

_NCBI_GENE_SUMMARY = {
    "result": {
        "uids": ["99999"],
        "99999": {
            "uid": "99999",
            "name": "FALLBACKGENE",
            "chromosome": "1",
            "genomicinfo": [
                {"chrloc": "1", "chrstart": 100000, "chrstop": 200000, "exoncount": 5}
            ],
        },
    }
}

_NCBI_GENE_SUMMARY_MINUS = {
    "result": {
        "uids": ["88888"],
        "88888": {
            "uid": "88888",
            "name": "MINUSGENE",
            "chromosome": "2",
            # chrstart > chrstop → minus strand
            "genomicinfo": [
                {"chrloc": "2", "chrstart": 500000, "chrstop": 400000, "exoncount": 3}
            ],
        },
    }
}

_NCBI_ELINK = {
    "linksets": [
        {
            "dbfrom": "gene",
            "ids": ["99999"],
            "linksetdbs": [
                {
                    "dbto": "nuccore",
                    "linkname": "gene_nuccore_refseqrna",
                    "links": ["111111", "222222"],
                }
            ],
        }
    ]
}

_NCBI_NUCCORE_SUMMARY = {
    "result": {
        "uids": ["111111", "222222"],
        "111111": {"uid": "111111", "accessionversion": "NM_001001.1"},
        "222222": {"uid": "222222", "accessionversion": "NM_001002.1"},
    }
}

_FASTA_NM_001001 = ">NM_001001.1 Homo sapiens fake gene, mRNA\nATGCATGCATGC\nTTTTGGGGCCCC\n"

_ENSEMBL_SEQ = {"id": "ENST00000376218", "seq": "ATGCCCGGGAAATTT"}

# Read from the config default rather than hardcoded: `ensembl_base_url` is
# a pinned release host since B17, and a copy of it here would silently
# stop matching the moment the pin moves (roadmap H9).
_BASE = OrcSonarConfig.model_fields["ensembl_base_url"].default
_NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def _ensembl_transcript_url(gene: str) -> str:
    return f"{_BASE}/lookup/symbol/homo_sapiens/{gene}?expand=1&content-type=application/json"


def _ensembl_seq_url(tid: str) -> str:
    return f"{_BASE}/sequence/id/{tid}?type=cdna&content-type=application/json"


def _esearch_url(gene: str) -> str:
    return (
        f"{_NCBI}esearch.fcgi"
        f"?db=gene&term={gene}[Gene+Name]+AND+Homo+sapiens[Organism]&retmode=json&retmax=1"
    )


def _esummary_gene_url(gid: str) -> str:
    return f"{_NCBI}esummary.fcgi?db=gene&id={gid}&retmode=json"


def _elink_url(gid: str) -> str:
    return (
        f"{_NCBI}elink.fcgi"
        f"?dbfrom=gene&db=nuccore&id={gid}&linkname=gene_nuccore_refseqrna&retmode=json"
    )


def _esummary_nuccore_url(ids: str) -> str:
    return f"{_NCBI}esummary.fcgi?db=nuccore&id={ids}&retmode=json"


def _efetch_url(acc: str) -> str:
    return f"{_NCBI}efetch.fcgi?db=nuccore&id={acc}&rettype=fasta&retmode=text"


# ---------------------------------------------------------------------------
# resolve_transcripts — Ensembl path
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_resolve_transcripts_ensembl_success(test_config: OrcSonarConfig) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("VEGFA"), json=_ENSEMBL_VEGFA)

    result = resolve_transcripts("VEGFA", test_config)

    assert len(result) == 2
    assert all(t.source == "Ensembl" for t in result)
    assert all(t.gene == "VEGFA" for t in result)
    assert all(t.chrom == "chr6" for t in result)


@resp_mock.activate
def test_canonical_transcript_is_flagged(test_config: OrcSonarConfig) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("VEGFA"), json=_ENSEMBL_VEGFA)

    result = resolve_transcripts("VEGFA", test_config)

    canonical = [t for t in result if t.is_canonical]
    assert len(canonical) == 1
    assert canonical[0].transcript_id == "ENST00000376218"


@resp_mock.activate
def test_canonical_promoted_to_longest_when_none_flagged(
    test_config: OrcSonarConfig,
) -> None:
    resp_mock.add(
        resp_mock.GET,
        _ensembl_transcript_url("NOCANONICALGENE"),
        json=_ENSEMBL_NO_CANONICAL,
    )

    result = resolve_transcripts("NOCANONICALGENE", test_config)

    canonical = [t for t in result if t.is_canonical]
    assert len(canonical) == 1
    # ENST00000002 spans 100 000 bp; ENST00000001 spans 50 000 bp
    assert canonical[0].transcript_id == "ENST00000002"


@resp_mock.activate
def test_chr_prefix_added_from_ensembl(test_config: OrcSonarConfig) -> None:
    """Ensembl seq_region_name '6' must become 'chr6'."""
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("VEGFA"), json=_ENSEMBL_VEGFA)

    result = resolve_transcripts("VEGFA", test_config)

    assert all(t.chrom == "chr6" for t in result)


@resp_mock.activate
def test_ensembl_minus_strand(test_config: OrcSonarConfig) -> None:
    payload = {**_ENSEMBL_VEGFA, "strand": -1,
               "Transcript": [{**_ENSEMBL_VEGFA["Transcript"][0], "strand": -1}]}
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("MINUSGENE"), json=payload)

    result = resolve_transcripts("MINUSGENE", test_config)

    assert result[0].strand == "-"


# ---------------------------------------------------------------------------
# resolve_transcripts — RefSeq fallback path
# ---------------------------------------------------------------------------


def _register_refseq_mocks() -> None:
    """Register all NCBI mock endpoints for FALLBACKGENE / gene_id 99999."""
    resp_mock.add(resp_mock.GET, _esearch_url("FALLBACKGENE"), json=_NCBI_ESEARCH)
    resp_mock.add(resp_mock.GET, _esummary_gene_url("99999"), json=_NCBI_GENE_SUMMARY)
    resp_mock.add(resp_mock.GET, _elink_url("99999"), json=_NCBI_ELINK)
    resp_mock.add(
        resp_mock.GET,
        _esummary_nuccore_url("111111,222222"),
        json=_NCBI_NUCCORE_SUMMARY,
    )


@resp_mock.activate
def test_resolve_transcripts_refseq_fallback(test_config: OrcSonarConfig) -> None:
    # Ensembl fails → RefSeq succeeds
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("FALLBACKGENE"), status=500)
    _register_refseq_mocks()

    result = resolve_transcripts("FALLBACKGENE", test_config)

    assert len(result) == 2
    assert all(t.source == "RefSeq" for t in result)
    assert result[0].transcript_id == "NM_001001.1"
    assert result[1].transcript_id == "NM_001002.1"


@resp_mock.activate
def test_refseq_first_accession_is_canonical(test_config: OrcSonarConfig) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("FALLBACKGENE"), status=500)
    _register_refseq_mocks()

    result = resolve_transcripts("FALLBACKGENE", test_config)

    assert result[0].is_canonical is True
    assert result[1].is_canonical is False


@resp_mock.activate
def test_refseq_gene_coordinates_plus_strand(test_config: OrcSonarConfig) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("FALLBACKGENE"), status=500)
    _register_refseq_mocks()

    result = resolve_transcripts("FALLBACKGENE", test_config)

    assert result[0].chrom == "chr1"
    assert result[0].start == 100000
    assert result[0].end == 200000
    assert result[0].strand == "+"


@resp_mock.activate
def test_refseq_minus_strand_gene(test_config: OrcSonarConfig) -> None:
    """chrstart > chrstop in NCBI esummary means minus strand."""
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("MINUSGENE"), status=500)
    resp_mock.add(
        resp_mock.GET,
        _esearch_url("MINUSGENE"),
        json={"esearchresult": {"idlist": ["88888"], "count": "1", "retmax": "1", "retstart": "0"}},
    )
    resp_mock.add(resp_mock.GET, _esummary_gene_url("88888"), json=_NCBI_GENE_SUMMARY_MINUS)
    resp_mock.add(
        resp_mock.GET, _elink_url("88888"),
        json={
            "linksets": [{"linksetdbs": [{"links": ["333333"]}]}]
        },
    )
    resp_mock.add(
        resp_mock.GET,
        _esummary_nuccore_url("333333"),
        json={
            "result": {
                "uids": ["333333"],
                "333333": {"uid": "333333", "accessionversion": "NM_002001.1"},
            }
        },
    )

    result = resolve_transcripts("MINUSGENE", test_config)

    assert result[0].strand == "-"
    assert result[0].start == 400000   # chrstop (smaller)
    assert result[0].end == 500000     # chrstart (larger)


@resp_mock.activate
def test_resolve_raises_datasource_error_when_both_fail(
    test_config: OrcSonarConfig,
) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("UNKNOWNGENE"), status=500)
    resp_mock.add(
        resp_mock.GET,
        _esearch_url("UNKNOWNGENE"),
        json={"esearchresult": {"idlist": [], "count": "0", "retmax": "1", "retstart": "0"}},
    )

    with pytest.raises(DataSourceError, match="UNKNOWNGENE"):
        resolve_transcripts("UNKNOWNGENE", test_config)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_transcript_list_cached_after_first_call(test_config: OrcSonarConfig) -> None:
    resp_mock.add(resp_mock.GET, _ensembl_transcript_url("VEGFA"), json=_ENSEMBL_VEGFA)

    resolve_transcripts("VEGFA", test_config)
    resolve_transcripts("VEGFA", test_config)  # should hit cache

    assert len(resp_mock.calls) == 1


@resp_mock.activate
def test_ncbi_esearch_none_on_empty_idlist(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        _esearch_url("NOTFOUND"),
        json={"esearchresult": {"idlist": [], "count": "0", "retmax": "1", "retstart": "0"}},
    )

    gene_id = _ncbi_esearch_gene_id("NOTFOUND", test_config)
    assert gene_id is None


# ---------------------------------------------------------------------------
# get_transcript_sequence
# ---------------------------------------------------------------------------


@resp_mock.activate
def test_get_sequence_ensembl_enst(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        _ensembl_seq_url("ENST00000376218"),
        json=_ENSEMBL_SEQ,
    )

    seq = get_transcript_sequence("ENST00000376218", test_config)

    assert seq == "ATGCCCGGGAAATTT"


@resp_mock.activate
def test_get_sequence_refseq_nm(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        _efetch_url("NM_001001.1"),
        body=_FASTA_NM_001001,
    )

    seq = get_transcript_sequence("NM_001001.1", test_config)

    assert seq == "ATGCATGCATGCTTTTGGGGCCCC"


@resp_mock.activate
def test_get_sequence_cached_after_first_call(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        _ensembl_seq_url("ENST00000376218"),
        json=_ENSEMBL_SEQ,
    )

    get_transcript_sequence("ENST00000376218", test_config)
    get_transcript_sequence("ENST00000376218", test_config)  # from cache

    assert len(resp_mock.calls) == 1


@resp_mock.activate
def test_get_sequence_raises_on_empty_ensembl_response(
    test_config: OrcSonarConfig,
) -> None:
    resp_mock.add(
        resp_mock.GET,
        _ensembl_seq_url("ENST00000000000"),
        json={"id": "ENST00000000000", "seq": ""},
    )

    with pytest.raises(DataSourceError, match="ENST00000000000"):
        get_transcript_sequence("ENST00000000000", test_config)


@resp_mock.activate
def test_get_sequence_raises_on_empty_refseq_fasta(
    test_config: OrcSonarConfig,
) -> None:
    resp_mock.add(
        resp_mock.GET,
        _efetch_url("NM_000000.1"),
        body=">NM_000000.1 empty record\n",
    )

    with pytest.raises(DataSourceError, match="NM_000000.1"):
        get_transcript_sequence("NM_000000.1", test_config)


@resp_mock.activate
def test_get_sequence_raises_on_api_error(test_config: OrcSonarConfig) -> None:
    resp_mock.add(
        resp_mock.GET,
        _ensembl_seq_url("ENST00000000001"),
        status=503,
    )

    with pytest.raises(DataSourceError):
        get_transcript_sequence("ENST00000000001", test_config)


class TestAFailedResolutionIsNotAnEmptyGene:
    """Losing the target gene's transcripts must not pass as "none found".

    Audit 2026-11-19. On failure `run()` wrote `{"transcripts": [], "count": 0}`
    and carried on. The target gene then contributes nothing to the scan: the
    search space silently shrinks to the background set, which is the Bulgu 12
    shape at one stage's remove, and the resulting report is a measurement of
    a different question.
    """

    def test_resolution_failure_raises_rather_than_writing_an_empty_gene(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "stage1_transcripts.json"
        with patch(
            "src.stage1_genomic_map.transcript_resolver.resolve_transcripts",
            side_effect=RuntimeError("Ensembl down"),
        ), pytest.raises(DataSourceError, match="transcript"):
            transcript_resolver_run(
                gene="VEGFA",
                ensembl_url=OrcSonarConfig.model_fields["ensembl_base_url"].default,
                ncbi_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
                output_path=str(out),
                log_path=str(tmp_path / "tr.log"),
            )
        assert not out.exists()
