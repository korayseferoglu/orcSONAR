"""Pydantic v2 data models for orcSONAR pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenomicRegion(BaseModel):
    """A genomic interval with strand information (hg38/GRCh38)."""

    chrom: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    strand: Literal["+", "-", "."] = "."

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: int, info: object) -> int:
        data = getattr(info, "data", {})
        if "start" in data and v < data["start"]:
            raise ValueError(f"end ({v}) must be >= start ({data['start']})")
        return v

    @property
    def length(self) -> int:
        return self.end - self.start

    def __str__(self) -> str:
        return f"{self.chrom}:{self.start}-{self.end}({self.strand})"


class SarnaInput(BaseModel):
    """User-supplied saRNA analysis request."""

    sequence: str = Field(min_length=10, max_length=30)
    target_gene: str
    cell_line: str

    @field_validator("sequence")
    @classmethod
    def uppercase_rna(cls, v: str) -> str:
        cleaned = v.upper().replace("T", "U")
        if not all(c in "ACGU" for c in cleaned):
            raise ValueError("sequence must contain only A/C/G/U (or T) bases")
        return cleaned


class TSSInfo(BaseModel):
    """Transcription start site record from EPDnew or FANTOM5."""

    gene: str
    chrom: str
    position: int = Field(ge=0)
    strand: Literal["+", "-"]
    source: Literal["EPDnew", "FANTOM5", "Ensembl", "RefSeq"]
    score: float = 0.0


class TranscriptInfo(BaseModel):
    """Transcript annotation record."""

    transcript_id: str
    gene: str
    chrom: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    strand: Literal["+", "-"]
    is_canonical: bool = False
    source: Literal["Ensembl", "RefSeq", "EPDnew"]


class AlignmentResult(BaseModel):
    """Intermediate result from seed_aligner._score_alignment."""

    score: float
    mismatches: int = Field(ge=0)
    gu_wobbles: int = Field(ge=0)
    seed_mismatches: int = Field(ge=0)
    aligned_target: str
    positions: list[int] = Field(default_factory=list)


class MirnaEntry(BaseModel):
    """A single mature miRNA record parsed from miRBase FASTA."""

    mirna_id: str
    accession: str
    sequence: str
    seed: str


class MirbaseOverlap(BaseModel):
    """Per-miRNA overlap result for one comparison."""

    mirna_id: str
    mirna_seed: str
    overlap_score: float
    matched_positions: int


class MirbaseResult(BaseModel):
    """Aggregated miRBase seed overlap result for a saRNA."""

    sarna_seed: str
    overlapping_mirnas: list[MirbaseOverlap] = Field(default_factory=list)
    max_overlap_score: float = 0.0
    risk_level: Literal["SAFE", "LOW", "MODERATE", "HIGH"] = "SAFE"


class OffTargetSite(BaseModel):
    """A candidate off-target binding site for the saRNA."""

    gene: str
    transcript_id: str
    region: GenomicRegion
    seed_match_type: Literal["perfect", "G:U_wobble", "mismatch", "bulge"]
    mismatches: int = Field(ge=0)
    alignment_score: float


class VariantScore(BaseModel):
    """Stage 3 — variant & toxicity sub-scores."""

    cosmic_count: int = 0
    cosmic_mutations: list[str] = Field(default_factory=list)
    gnomad_max_af: float = 0.0
    clinvar_pathogenic: bool = False
    phylop_score: float = 0.0
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class EpigeneticScore(BaseModel):
    """Stage 4 — epigenetic & topology sub-scores."""

    atac_signal: float = 0.0
    h3k4me3_signal: float = 0.0
    h3k27ac_signal: float = 0.0
    groseq_signal: float = 0.0
    hic_contact: float = 0.0
    ccle_expression: float = 0.0
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class BiophysicsScore(BaseModel):
    """Stage 5 — biophysics & structural sub-scores."""

    delta_g: float = 0.0
    shape_accessibility: float = 0.0
    m6a_sites: int = 0
    adar_risk: float = 0.0
    g4_risk: float = 0.0
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class ExecutionScore(BaseModel):
    """Stage 6 — execution & safety sub-scores."""

    ago2_loading: float = 0.0
    rbp_competition: float = 0.0
    circrna_overlap: bool = False
    immune_motif_count: int = 0
    immune_motifs_found: list[str] = Field(default_factory=list)
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class DomainScores(BaseModel):
    """Aggregated domain scores for a single off-target site."""

    sequence_specificity: float = Field(ge=0.0, le=1.0, default=0.5)
    variant_toxicity: float = Field(ge=0.0, le=1.0, default=0.5)
    epigenetic_context: float = Field(ge=0.0, le=1.0, default=0.5)
    biophysics_structure: float = Field(ge=0.0, le=1.0, default=0.5)
    execution_safety: float = Field(ge=0.0, le=1.0, default=0.5)


RiskClass = Literal["SAFE", "WARNING", "HIGH_RISK", "DANGEROUS"]


class FinalReport(BaseModel):
    """Top-level orcSONAR analysis result."""

    sarna_input: SarnaInput
    offtarget_sites: list[OffTargetSite] = Field(default_factory=list)
    domain_scores_per_site: dict[str, DomainScores] = Field(default_factory=dict)
    final_risk_score: float = Field(ge=0.0, le=1.0)
    risk_class: RiskClass
    cell_line_context: str
