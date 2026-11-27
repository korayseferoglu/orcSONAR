"""Pydantic v2 data models for orcSONAR pipeline."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field, field_validator


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
    """Aggregated miRBase seed overlap result for a saRNA.

    ``max_overlap_score`` and ``risk_level`` are ``None`` when the check could
    not run — invariant 2's shape, and roadmap `B11`'s subject. They used to
    default to ``0.0`` and ``"SAFE"``, which meant every half-built result
    claimed safety and a missing FASTA was indistinguishable from a measured
    absence of overlap. The two cases are now different values, and the
    distinction is the same one `_bigwig_mean` already draws between "contig
    absent" and "signal measured 0".
    """

    sarna_seed: str
    overlapping_mirnas: list[MirbaseOverlap] = Field(default_factory=list)
    #: ``None`` = never measured. A readable FASTA with no human overlap is a
    #: measured ``0.0``, which is a different statement.
    max_overlap_score: float | None = None
    risk_level: Literal["SAFE", "LOW", "MODERATE", "HIGH"] | None = None


class OffTargetSite(BaseModel):
    """A candidate off-target binding site for the saRNA."""

    gene: str
    transcript_id: str
    region: GenomicRegion
    seed_match_type: Literal["perfect", "G:U_wobble", "mismatch", "bulge"]
    mismatches: int = Field(ge=0)
    alignment_score: float
    tx_start: int | None = Field(default=None, ge=0)
    tx_end: int | None = Field(default=None, ge=0)
    #: The transcript slice this site was scored against, 5'→3', same length
    #: as the guide. Carried from stage 2 because stage 5 otherwise has no
    #: access to the off-target sequence and used the saRNA's own reverse
    #: complement instead — one identical ΔG for every site in a run
    #: (roadmap C3). Added after tx_end on purpose: `site_id`'s field order
    #: is load-bearing and must not move.
    target_window: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def site_id(self) -> str:
        """Canonical identity of this site, unique across a run.

        The seed scan can return several hits for one transcript, so
        ``gene:transcript_id`` alone is NOT unique — keying a dict on it makes
        one hit silently overwrite another (AUDIT.md Bulgu-2). The locus is
        what separates them.

        FIELD ORDER IS LOAD-BEARING and pinned by
        ``tests/unit/test_models.py::test_site_id_layout``:

        * field 0 is the gene — ``epigenetic_merger`` recovers it with
          ``split(":", 1)[0]`` for the CCLE lookup, which is keyed by gene.
        * field 1 is the transcript — ``templates/report.html`` renders it.

        Reordering these breaks both silently: the CCLE lookup would miss for
        every site and degrade to 0.0, still producing in-range scores.

        Strand is deliberately absent: it comes from the transcript, so with
        ``transcript_id`` already present it disambiguates nothing. It stays
        available on ``region.strand``.

        The number is ``region.start`` as the aligner produced it — an
        identifier, not a display coordinate. Never parse it back out to do
        arithmetic; ``region`` is the source of truth for coordinates.
        """
        return f"{self.gene}:{self.transcript_id}:{self.region.chrom}:{self.region.start}"


class RepeatEntry(BaseModel):
    """A single RepeatMasker annotation from UCSC rmsk track."""

    chrom: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    rep_name: str
    rep_class: str
    rep_family: str


class RepeatResult(BaseModel):
    """Repeat scan result for one genomic region (Stage 2)."""

    region: GenomicRegion
    repeats: list[RepeatEntry] = Field(default_factory=list)
    has_alu: bool = False
    has_line: bool = False
    adar_risk_score: float = Field(ge=0.0, le=1.0, default=0.0)


class CosmicMutation(BaseModel):
    """A single COSMIC cancer mutation record parsed from the VCF."""

    position: int = Field(ge=0)
    ref: str
    alt: str
    gene: str
    so_term: str
    sample_count: int = Field(ge=0, default=0)
    tier: int | None = None  # 1 or 2 if in Cancer Gene Census; None otherwise


class CosmicResult(BaseModel):
    """COSMIC scan result for one off-target genomic region (Stage 3)."""

    region: GenomicRegion
    mutations: list[CosmicMutation] = Field(default_factory=list)
    # None where the source could not be read: a failed VCF is not "no
    # mutations here" (audit 2026-11-19, Bulgu 2).
    mutation_count: int | None = Field(ge=0, default=None)
    has_tier1_gene: bool | None = None
    density_score: float | None = Field(ge=0.0, le=1.0, default=None)


class ClinvarVariant(BaseModel):
    """A single ClinVar variant (pathogenic or likely pathogenic)."""

    uid: str
    position: int | None = None
    significance: str
    condition: str = ""
    gene: str = ""


class ClinvarResult(BaseModel):
    """ClinVar check result for one off-target genomic region (Stage 3)."""

    region: GenomicRegion
    pathogenic_count: int = Field(ge=0, default=0)
    likely_pathogenic_count: int = Field(ge=0, default=0)
    variants: list[ClinvarVariant] = Field(default_factory=list)


class GnomadVariant(BaseModel):
    """A single variant record from gnomAD population database."""

    variant_id: str
    position: int = Field(ge=0)
    ref: str
    alt: str
    allele_frequency: float = Field(ge=0.0, le=1.0, default=0.0)


class GnomadResult(BaseModel):
    """gnomAD polymorphism scan result for one off-target region (Stage 3)."""

    region: GenomicRegion
    variants: list[GnomadVariant] = Field(default_factory=list)
    variant_count: int | None = Field(ge=0, default=None)
    max_af: float | None = Field(ge=0.0, le=1.0, default=None)
    polymorphism_score: float | None = Field(ge=0.0, le=1.0, default=None)


class PhylopResult(BaseModel):
    """phyloP evolutionary conservation result for one off-target region (Stage 3)."""

    region: GenomicRegion
    mean_score: float | None = None  # raw phyloP value (can be negative)
    conservation_score: float | None = Field(ge=0.0, le=1.0, default=None)


class VariantScore(BaseModel):
    """Stage 3 — variant & toxicity sub-scores."""

    cosmic_count: int = 0
    cosmic_mutations: list[str] = Field(default_factory=list)
    gnomad_max_af: float = 0.0
    clinvar_pathogenic: bool = False
    phylop_score: float = 0.0
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class CCLEResult(BaseModel):
    """CCLE gene expression result for one (gene, cell line) pair (Stage 4)."""

    gene: str
    cell_line: str
    # `None` means not measured (roadmap B19). The old 0.0/False defaults were
    # the fourth fallback B2 missed, and the worst-directed one: an expression
    # of 0.0 reads as "not expressed", which reads as "cannot be silenced",
    # which reads as **lower risk** — for a gene nobody looked up. Reached
    # whenever the cell line has no DepMap model (HEK293T, GM12878) or the gene
    # is absent from the CCLE header.
    expression_value: float | None = None
    is_expressed: bool | None = None
    expression_percentile: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class HiCResult(BaseModel):
    """Hi-C 3D contact result between two genomic regions (Stage 4)."""

    target_region: GenomicRegion
    offtarget_region: GenomicRegion
    contact_frequency: float = 0.0


class GROseqResult(BaseModel):
    """GRO-seq transcriptional activity result for one region (Stage 4)."""

    region: GenomicRegion
    # `None` means not measured, which is not the same as a measured 0.0:
    # for every signal in this stage, less signal reads as lower risk
    # (roadmap B2, AUDIT.md Bulgu-10).
    plus_signal: float | None = None
    minus_signal: float | None = None
    combined_signal: float | None = None


class EpigeneticScore(BaseModel):
    """Stage 4 — epigenetic & topology sub-scores."""

    # Raw signals stay in native units (rule 10) and are `None` when the
    # source could not be read. The old 0.0 defaults made an unread source
    # indistinguishable from a silent locus, and silence lowers risk (B2).
    atac_signal: float | None = None
    h3k4me3_signal: float | None = None
    h3k27ac_signal: float | None = None
    groseq_signal: float | None = None
    hic_contact: float | None = None
    ccle_expression: float | None = None
    # `None` when no channel was measured at all. The old 0.5 default was a
    # number nobody measured; roadmap B3 adds the coverage threshold that
    # decides when a score may be produced.
    normalized_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ThermoResult(BaseModel):
    """Nearest-neighbor ΔG result for a saRNA:mRNA duplex (Stage 5)."""

    delta_g: float
    delta_h: float = 0.0
    stack_energies: list[float] = Field(default_factory=list)
    has_mismatches: bool = False
    mismatch_penalties: list[float] = Field(default_factory=list)


class ShapeResult(BaseModel):
    """SHAPE-Seq accessibility result for one genomic region (Stage 5)."""

    region: GenomicRegion
    # None when no icSHAPE data was consulted: 0.5 was written both for a
    # measured mid-reactivity and for a missing file (audit Bulgu 2).
    mean_reactivity: float | None = None
    accessibility_score: float | None = Field(ge=0.0, le=1.0, default=None)
    single_stranded_fraction: float | None = Field(ge=0.0, le=1.0, default=None)
    data_available: bool = False


class M6ASite(BaseModel):
    """A single m6A modification site from RMBase (Stage 5)."""

    chrom: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    strand: Literal["+", "-", "."] = "."
    mod_type: str = "m6A"
    cell_line: str = ""
    gene: str = ""


class M6AResult(BaseModel):
    """m6A site scan result for one genomic region (Stage 5)."""

    region: GenomicRegion
    cell_line: str
    sites: list[M6ASite] = Field(default_factory=list)
    site_count: int | None = Field(ge=0, default=None)
    m6a_score: float | None = Field(ge=0.0, le=1.0, default=None)


class AdarRiskResult(BaseModel):
    """ADAR A-to-I editing risk for one genomic region (Stage 5)."""

    region: GenomicRegion
    alu_risk: float | None = Field(ge=0.0, le=1.0, default=None)
    shape_ds_risk: float | None = Field(ge=0.0, le=1.0, default=None)
    adar_score: float | None = Field(ge=0.0, le=1.0, default=None)
    shape_used: bool = False


class G4Motif(BaseModel):
    """A single G-Quadruplex motif found in a sequence (Stage 5)."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    sequence: str
    strand: Literal["+", "-"] = "+"
    g_tract_lengths: list[int] = Field(default_factory=list)
    loop_lengths: list[int] = Field(default_factory=list)
    stability_score: float = Field(ge=0.0, le=1.0, default=0.0)


class G4Result(BaseModel):
    """G4 structure detection result for a nucleotide sequence (Stage 5)."""

    motifs: list[G4Motif] = Field(default_factory=list)
    g4_count: int | None = Field(ge=0, default=None)
    g4_density: float | None = None  # motifs per kb
    risk_score: float | None = Field(ge=0.0, le=1.0, default=None)


class BiophysicsScore(BaseModel):
    """Stage 5 — biophysics & structural sub-scores."""

    delta_g: float = 0.0
    shape_accessibility: float = 0.0
    m6a_sites: int = 0
    adar_risk: float = 0.0
    g4_risk: float = 0.0
    normalized_score: float = Field(ge=0.0, le=1.0, default=0.5)


class Ago2Result(BaseModel):
    """Ago2 eCLIP RISC-loading result for one genomic region (Stage 6)."""

    region: GenomicRegion
    cell_line: str
    raw_signal: float | None = None
    loading_score: float | None = Field(default=None, ge=0.0, le=1.0)
    # `None` when loading_score is unknown: a verdict derived from an
    # unmeasured signal is itself unknown, and `False` would assert "not
    # loaded" — the safe-looking direction B2 removes.
    is_loaded: bool | None = None


class RBPResult(BaseModel):
    """RBP competition result for one genomic region (Stage 6)."""

    region: GenomicRegion
    cell_line: str
    rbp_name: str = "hnRNPA1"
    raw_signal: float | None = None
    competition_score: float | None = Field(default=None, ge=0.0, le=1.0)
    # `None` when competition_score is unknown (see Ago2Result.is_loaded).
    is_competing: bool | None = None


class CircRNAEntry(BaseModel):
    """A single circular RNA record from circAtlas BED (Stage 6)."""

    chrom: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    circ_id: str
    strand: Literal["+", "-", "."] = "."


class CircRNAResult(BaseModel):
    """circRNA sponge overlap result for one genomic region (Stage 6)."""

    region: GenomicRegion
    overlapping_circrnas: list[CircRNAEntry] = Field(default_factory=list)
    overlap_count: int = Field(ge=0, default=0)
    sponge_risk: bool = False
    data_available: bool = False


class MotifHit(BaseModel):
    """A single TLR7/TLR8 immune motif hit in a saRNA sequence (Stage 6)."""

    motif: str
    position: int = Field(ge=0)
    strand: Literal["+", "-"]


class ImmuneResult(BaseModel):
    """Immune motif screen result for a saRNA sequence (Stage 6)."""

    motifs_found: list[MotifHit] = Field(default_factory=list)
    total_hits: int = Field(ge=0, default=0)
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    risk_level: str = "SAFE"


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
    # Both are ``None`` when no site was classified: a run that assessed
    # nothing has no overall risk, and writing 0.0/SAFE there turned an empty
    # scan into a verdict of safety (audit 2026-11-19, Bulgu 12).
    final_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_class: RiskClass | None = None
    cell_line_context: str
