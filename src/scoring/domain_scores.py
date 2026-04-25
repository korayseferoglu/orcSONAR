"""Domain score normalisation functions for Stage 7 orcSONAR scoring.

Each function converts raw outputs from one pipeline domain into a [0, 1]
risk score that can be weighted and combined by the integrator.

Normalisation strategies:
- Sequence Specificity : binary logic + severity (seed hit type counts)
- Variant Toxicity     : min-max / weighted components (COSMIC density, ClinVar)
- Epigenetic Context   : saturation scaling of BigWig signals
- Biophysics Structure : sigmoid for ΔG; direct scores for SHAPE/m6A/ADAR/G4
- Execution Safety     : loading scores + binary flags (Ago2, circRNA, immune)
"""

from __future__ import annotations

import math

from loguru import logger

from src.core.models import (
    AdarRiskResult,
    Ago2Result,
    CircRNAResult,
    ClinvarResult,
    CosmicResult,
    G4Result,
    GnomadResult,
    ImmuneResult,
    M6AResult,
    MirbaseResult,
    OffTargetSite,
    PhylopResult,
    RBPResult,
    RepeatResult,
    ShapeResult,
    ThermoResult,
)

# ---------------------------------------------------------------------------
# Saturation constants for epigenetic signals (BigWig fold-change)
# ---------------------------------------------------------------------------
_ATAC_SAT: float = 10.0     # ATAC-seq FC at which risk saturates to 1.0
_HISTONE_SAT: float = 15.0  # H3K4me3/H3K27ac FC saturation
_GROSEQ_SAT: float = 5.0    # GRO-seq combined signal saturation
_HIC_SAT: float = 0.2       # Hi-C contact frequency saturation
_CCLE_SAT: float = 6.0      # CCLE log2(TPM+1) saturation


def normalize_sequence_score(
    seed_hits: list[OffTargetSite],
    mirbase_result: MirbaseResult,
    repeat_result: RepeatResult,
) -> float:
    """Normalise Stage 2 off-target seed / miRNA / repeat signals to [0, 1].

    Risk increases with perfect seed matches, miRBase overlap, and repeat
    (ADAR) risk.  G:U wobble hits contribute less than perfect matches.

    Args:
        seed_hits: Off-target sites from the Stage 2 seed aligner.
        mirbase_result: miRBase seed overlap result.
        repeat_result: RepeatMasker repeat scan result.

    Returns:
        Normalised sequence specificity risk score in [0, 1].
    """
    perfect = sum(1 for h in seed_hits if h.seed_match_type == "perfect")
    wobble = sum(1 for h in seed_hits if h.seed_match_type == "G:U_wobble")
    mismatch = sum(
        1 for h in seed_hits if h.seed_match_type in ("mismatch", "bulge")
    )

    # Each perfect hit is strongly penalised; wobble hits moderately; mismatches lightly.
    seed_component = min(1.0, perfect * 0.40 + wobble * 0.20 + mismatch * 0.05)

    mirbase_component = mirbase_result.max_overlap_score
    repeat_component = repeat_result.adar_risk_score

    score = (
        0.50 * seed_component
        + 0.30 * mirbase_component
        + 0.20 * repeat_component
    )
    result = max(0.0, min(1.0, score))

    logger.debug(
        f"sequence_score: perfect={perfect} wobble={wobble} mismatch={mismatch} "
        f"seed={seed_component:.3f} mirbase={mirbase_component:.3f} "
        f"repeat={repeat_component:.3f} → {result:.3f}"
    )
    return result


def normalize_variant_score(
    cosmic: CosmicResult,
    gnomad: GnomadResult,
    clinvar: ClinvarResult,
    phylop: PhylopResult,
) -> float:
    """Normalise Stage 3 variant / toxicity signals to [0, 1].

    High COSMIC density, ClinVar pathogenic variants, and high conservation
    (phyloP) all increase the score.  Common gnomAD variants slightly reduce
    it (highly polymorphic sites are functionally less critical).

    Args:
        cosmic: COSMIC cancer mutation scan result.
        gnomad: gnomAD population variant result.
        clinvar: ClinVar pathogenicity result.
        phylop: phyloP evolutionary conservation result.

    Returns:
        Normalised variant toxicity risk score in [0, 1].
    """
    # Tier-1 Cancer Gene Census membership amplifies COSMIC risk.
    cosmic_component = min(
        1.0, cosmic.density_score + (0.30 if cosmic.has_tier1_gene else 0.0)
    )

    clinvar_component = min(
        1.0,
        clinvar.pathogenic_count * 0.40 + clinvar.likely_pathogenic_count * 0.20,
    )

    phylop_component = phylop.conservation_score

    # High gnomAD allele frequency = common benign variant → slightly lowers risk.
    gnomad_reduction = gnomad.max_af * 0.30

    raw = (
        0.40 * cosmic_component
        + 0.30 * clinvar_component
        + 0.30 * phylop_component
    )
    result = max(0.0, min(1.0, raw - gnomad_reduction))

    logger.debug(
        f"variant_score: cosmic={cosmic_component:.3f} clinvar={clinvar_component:.3f} "
        f"phylop={phylop_component:.3f} gnomad_red={gnomad_reduction:.3f} → {result:.3f}"
    )
    return result


def normalize_epigenetic_score(
    atac: float,
    histones: dict[str, float],
    groseq: float,
    hic: float,
    ccle: float,
) -> float:
    """Normalise Stage 4 epigenetic / topology signals to [0, 1].

    Open chromatin (ATAC + H3K4me3/H3K27ac), active transcription (GRO-seq),
    3D proximity (Hi-C), and gene expression (CCLE) all elevate risk.
    Repressive H3K27me3 reduces the active histone contribution.

    Args:
        atac: Raw ATAC-seq fold-change signal.
        histones: Dict of histone mark signals; expected keys: ``h3k4me3``,
            ``h3k27ac``, ``h3k27me3``.  Missing keys default to 0.
        groseq: GRO-seq combined strand signal.
        hic: Hi-C contact frequency between target and off-target loci.
        ccle: CCLE gene expression value, log2(TPM+1).

    Returns:
        Normalised epigenetic context risk score in [0, 1].
    """
    atac_score = min(1.0, max(0.0, atac) / _ATAC_SAT)
    h3k4me3_score = min(1.0, max(0.0, histones.get("h3k4me3", 0.0)) / _HISTONE_SAT)
    h3k27ac_score = min(1.0, max(0.0, histones.get("h3k27ac", 0.0)) / _HISTONE_SAT)
    h3k27me3_score = min(1.0, max(0.0, histones.get("h3k27me3", 0.0)) / _HISTONE_SAT)
    groseq_score = min(1.0, max(0.0, groseq) / _GROSEQ_SAT)
    hic_score = min(1.0, max(0.0, hic) / _HIC_SAT)
    ccle_score = min(1.0, max(0.0, ccle) / _CCLE_SAT)

    # H3K27me3 (repressive) offsets active histone marks.
    active_histone = (h3k4me3_score + h3k27ac_score) / 2.0
    histone_score = max(0.0, active_histone - h3k27me3_score * 0.50)

    score = (
        0.25 * atac_score
        + 0.20 * histone_score
        + 0.15 * groseq_score
        + 0.15 * hic_score
        + 0.25 * ccle_score
    )
    result = max(0.0, min(1.0, score))

    logger.debug(
        f"epigenetic_score: atac={atac_score:.3f} histone={histone_score:.3f} "
        f"groseq={groseq_score:.3f} hic={hic_score:.3f} ccle={ccle_score:.3f} → {result:.3f}"
    )
    return result


def normalize_biophysics_score(
    thermo: ThermoResult,
    shape: ShapeResult,
    m6a: M6AResult,
    adar: AdarRiskResult,
    g4: G4Result,
) -> float:
    """Normalise Stage 5 biophysics / structural signals to [0, 1].

    ΔG is converted via a sigmoid so that very negative values (stable duplexes)
    yield high risk.  SHAPE accessibility, m6A density, ADAR risk, and G4
    propensity contribute additively.

    Sigmoid formula for ΔG:
        thermo_risk = 1 / (1 + exp(ΔG/5 + 2))
        At ΔG = -30 → ≈ 0.98 (very stable → high risk)
        At ΔG = -10 → 0.50 (moderate)
        At ΔG =   0 → ≈ 0.12 (weak binding → low risk)

    Args:
        thermo: Nearest-neighbour ΔG result for the saRNA:mRNA duplex.
        shape: SHAPE-seq accessibility result for the off-target region.
        m6a: m6A modification site scan result.
        adar: ADAR A-to-I editing risk result.
        g4: G-Quadruplex detection result.

    Returns:
        Normalised biophysics structure risk score in [0, 1].
    """
    thermo_risk = 1.0 / (1.0 + math.exp(thermo.delta_g / 5.0 + 2.0))
    shape_risk = shape.accessibility_score if shape.data_available else 0.5
    m6a_risk = m6a.m6a_score
    adar_risk = adar.adar_score
    g4_risk = g4.risk_score

    score = (
        0.35 * thermo_risk
        + 0.25 * shape_risk
        + 0.15 * m6a_risk
        + 0.15 * adar_risk
        + 0.10 * g4_risk
    )
    result = max(0.0, min(1.0, score))

    logger.debug(
        f"biophysics_score: dG={thermo.delta_g:.1f} thermo={thermo_risk:.3f} "
        f"shape={shape_risk:.3f} m6a={m6a_risk:.3f} adar={adar_risk:.3f} "
        f"g4={g4_risk:.3f} → {result:.3f}"
    )
    return result


def normalize_execution_score(
    ago2: Ago2Result,
    rbp: RBPResult,
    circrna: CircRNAResult,
    immune: ImmuneResult,
) -> float:
    """Normalise Stage 6 execution / safety signals to [0, 1].

    Ago2 RISC loading and immune motifs are the primary risk drivers.
    circRNA sponge risk adds a binary component.  RBP competition at the
    off-target region marks it as a regulatory hotspot (moderate risk).

    Args:
        ago2: Ago2 eCLIP RISC-loading result.
        rbp: RBP competition result for the off-target region.
        circrna: circRNA sponge overlap result.
        immune: TLR7/TLR8 immune motif screen result.

    Returns:
        Normalised execution safety risk score in [0, 1].
    """
    ago2_risk = ago2.loading_score

    # RBP competition marks the region as regulatory-active → moderate risk amplifier.
    rbp_risk = rbp.competition_score * 0.50

    if circrna.sponge_risk:
        circrna_risk = 1.0
    elif circrna.data_available:
        circrna_risk = min(1.0, circrna.overlap_count * 0.25)
    else:
        circrna_risk = 0.0

    immune_risk = immune.risk_score

    score = (
        0.35 * ago2_risk
        + 0.15 * rbp_risk
        + 0.20 * circrna_risk
        + 0.30 * immune_risk
    )
    result = max(0.0, min(1.0, score))

    logger.debug(
        f"execution_score: ago2={ago2_risk:.3f} rbp={rbp_risk:.3f} "
        f"circrna={circrna_risk:.3f} immune={immune_risk:.3f} → {result:.3f}"
    )
    return result
