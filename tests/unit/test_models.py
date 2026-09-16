"""Unit tests for src/core/models.py."""

import pytest
from pydantic import ValidationError

from src.core.models import (
    BiophysicsScore,
    DomainScores,
    EpigeneticScore,
    ExecutionScore,
    FinalReport,
    GenomicRegion,
    OffTargetSite,
    SarnaInput,
    TSSInfo,
    TranscriptInfo,
    VariantScore,
)


class TestGenomicRegion:
    def test_basic(self):
        r = GenomicRegion(chrom="chr1", start=100, end=200, strand="+")
        assert r.length == 100
        assert str(r) == "chr1:100-200(+)"

    def test_default_strand(self):
        r = GenomicRegion(chrom="chrX", start=0, end=50)
        assert r.strand == "."

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError):
            GenomicRegion(chrom="chr1", start=300, end=100)

    def test_negative_start_raises(self):
        with pytest.raises(ValidationError):
            GenomicRegion(chrom="chr1", start=-1, end=100)


class TestSarnaInput:
    def test_t_converted_to_u(self):
        s = SarnaInput(sequence="GCAACCATAGCCTCGGCCGC", target_gene="VEGFA", cell_line="HeLa")
        # T → U conversion
        assert "T" not in s.sequence

    def test_lowercase_normalised(self):
        s = SarnaInput(sequence="gcaaccauagccucggccgc", target_gene="VEGFA", cell_line="HeLa")
        assert s.sequence == "GCAACCAUAGCCUCGGCCGC"

    def test_invalid_base_raises(self):
        with pytest.raises(ValidationError):
            SarnaInput(sequence="GCAACCAXAGCCTCGGCCGC", target_gene="VEGFA", cell_line="HeLa")

    def test_too_short_raises(self):
        with pytest.raises(ValidationError):
            SarnaInput(sequence="GCAA", target_gene="VEGFA", cell_line="HeLa")

    def test_too_long_raises(self):
        with pytest.raises(ValidationError):
            SarnaInput(sequence="G" * 31, target_gene="VEGFA", cell_line="HeLa")


class TestTSSInfo:
    def test_valid(self):
        t = TSSInfo(gene="VEGFA", chrom="chr6", position=43770000, strand="+", source="EPDnew")
        assert t.gene == "VEGFA"


class TestTranscriptInfo:
    def test_valid(self):
        t = TranscriptInfo(
            transcript_id="ENST00000001",
            gene="VEGFA",
            chrom="chr6",
            start=43768000,
            end=43786487,
            strand="+",
            is_canonical=True,
            source="Ensembl",
        )
        assert t.is_canonical is True


class TestOffTargetSite:
    def test_valid(self, sample_region):
        site = OffTargetSite(
            gene="MYC",
            transcript_id="ENST00000377970",
            region=sample_region,
            seed_match_type="perfect",
            mismatches=0,
            alignment_score=0.95,
        )
        assert site.mismatches == 0

    def test_site_id_layout(self, sample_region):
        """Pin the site_id field order — downstream code parses it positionally.

        epigenetic_merger recovers the gene with split(":", 1)[0] for the CCLE
        lookup, and templates/report.html renders field 1 as the transcript.
        Reordering breaks both silently (AUDIT.md Bulgu-2).
        """
        site = OffTargetSite(
            gene="MTOR",
            transcript_id="ENST00000361445",
            region=sample_region,
            seed_match_type="mismatch",
            mismatches=5,
            alignment_score=14.5,
        )
        parts = site.site_id.split(":")
        assert len(parts) == 4
        assert parts[0] == "MTOR"
        assert parts[1] == "ENST00000361445"
        assert parts[2] == sample_region.chrom
        assert parts[3] == str(sample_region.start)
        assert site.model_dump()["site_id"] == site.site_id

    def test_site_id_distinguishes_hits_on_one_transcript(self, sample_region):
        """Two windows on the same transcript must not share an id (Bulgu-2)."""
        common = {
            "gene": "MTOR",
            "transcript_id": "ENST00000361445",
            "seed_match_type": "mismatch",
            "alignment_score": 14.5,
        }
        a = OffTargetSite(
            region=GenomicRegion(chrom="chr1", start=11255438, end=11255458, strand="-"),
            mismatches=5,
            **common,
        )
        b = OffTargetSite(
            region=GenomicRegion(chrom="chr1", start=11259515, end=11259535, strand="-"),
            mismatches=9,
            **common,
        )
        assert a.site_id != b.site_id
        assert len({a.site_id, b.site_id}) == 2

    def test_negative_mismatches_raises(self, sample_region):
        with pytest.raises(ValidationError):
            OffTargetSite(
                gene="MYC",
                transcript_id="ENST00000377970",
                region=sample_region,
                seed_match_type="perfect",
                mismatches=-1,
                alignment_score=0.9,
            )


class TestNormalisedScores:
    def test_variant_score_defaults(self):
        v = VariantScore()
        assert 0.0 <= v.normalized_score <= 1.0

    def test_epigenetic_score_defaults(self):
        e = EpigeneticScore()
        assert 0.0 <= e.normalized_score <= 1.0

    def test_biophysics_score_defaults(self):
        b = BiophysicsScore()
        assert 0.0 <= b.normalized_score <= 1.0

    def test_execution_score_defaults(self):
        ex = ExecutionScore()
        assert 0.0 <= ex.normalized_score <= 1.0

    def test_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            VariantScore(normalized_score=1.5)


class TestFinalReport:
    def test_valid(self, sample_sarna_input):
        report = FinalReport(
            sarna_input=sample_sarna_input,
            final_risk_score=0.25,
            risk_class="SAFE",
            cell_line_context="HeLa",
        )
        assert report.risk_class == "SAFE"
        assert report.offtarget_sites == []

    def test_invalid_risk_score_raises(self, sample_sarna_input):
        with pytest.raises(ValidationError):
            FinalReport(
                sarna_input=sample_sarna_input,
                final_risk_score=1.5,
                risk_class="SAFE",
                cell_line_context="HeLa",
            )
