"""YAML-based configuration loader using Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringWeights(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    sequence_specificity: float = 0.20
    variant_toxicity: float = 0.15
    biophysics_structure: float = 0.25
    epigenetic_context: float = 0.20
    execution_safety: float = 0.20

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ScoringWeights":
        total = (
            self.sequence_specificity
            + self.variant_toxicity
            + self.biophysics_structure
            + self.epigenetic_context
            + self.execution_safety
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring_weights must sum to 1.0, got {total:.4f}")
        return self


class RiskThresholds(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid")

    safe: float = 0.3
    warning: float = 0.6
    high_risk: float = 0.8


class DataPaths(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    epdnew_bed: str = "data/1_Temel_Harita/EPDnew/EPDnew_hg38.bed"
    fantom5_bed: str = "data/1_Temel_Harita/FANTOM5/FANTOM5_hg38_CAGE_peaks.bed"
    mirbase_fa: str = "data/1_Temel_Harita/miRBase/mature.fa"
    cosmic_vcf: str = "data/2_Varyant_Toksisite/COSMIC/Cosmic_GenomeScreensMutant_v103_GRCh38.vcf.gz"
    ccle_csv: str = "data/3_Topoloji_Epigenetik/CCLE/CCLE_Expression.csv"
    turner_rules_dir: str = "data/4_Biyofizik_Yapısal/Turner_Rules"
    shape_seq_dir: str = "data/4_Biyofizik_Yapısal/SHAPE_Seq"
    m6a_bed: str = "data/4_Biyofizik_Yapısal/RMBase/hg38_m6A_mühürlü.bed.gz"
    immune_motifs: str = "data/5_Icra_Güvenlik/Immun_Motifler/immune_motifs.txt"
    circrna_dir: str = "data/5_Icra_Güvenlik/circAtlas"
    rbp_dir: str = "data/5_Icra_Güvenlik/POSTAR3"
    cache_db: str = "data/cache/orcsonar_cache.db"


class OrcSonarConfig(BaseSettings):
    """Full orcSONAR runtime configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    # Analysis target
    target_gene: str = "VEGFA"
    cell_line: str = "HeLa"
    sarna_sequence: str = "GCAACCATAGCCTCGGCCGC"

    # Promoter window
    promoter_upstream: int = 1000
    promoter_downstream: int = 200

    # Thermodynamic thresholds
    delta_g_strong: float = -30.0
    delta_g_moderate: float = -25.0

    # Seed alignment
    seed_length: int = 7
    max_mismatches: int = 3
    gc_range: list[float] = Field(default=[35.0, 65.0])

    # Remote URLs
    phylop_bigwig_url: str = "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw"
    ensembl_base_url: str = "https://rest.ensembl.org"
    gnomad_api_url: str = "https://gnomad.broadinstitute.org/api"
    ncbi_eutils_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    ucsc_api_url: str = "https://api.genome.ucsc.edu/getData/track"
    encode_portal_url: str = "https://www.encodeproject.org"

    supported_cell_lines: list[str] = Field(
        default=["A549", "GM12878", "HEK293T", "HeLa", "HepG2", "Huh7", "K562", "MCF7"]
    )

    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    risk_thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    data_paths: DataPaths = Field(default_factory=DataPaths)

    results_dir: str = "results"
    logs_dir: str = "logs"

    @field_validator("cell_line")
    @classmethod
    def valid_cell_line(cls, v: str) -> str:
        valid = ["A549", "GM12878", "HEK293T", "HeLa", "HepG2", "Huh7", "K562", "MCF7"]
        if v not in valid:
            raise ValueError(f"cell_line must be one of {valid}, got '{v}'")
        return v


def _flatten(d: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    """Merge nested YAML sections into a flat dict for Pydantic."""
    for k, v in d.items():
        if isinstance(v, dict):
            parent[k] = v  # pass nested dicts as-is (Pydantic handles sub-models)
        else:
            parent[k] = v
    return parent


def load_config(path: str | Path = "config/config.yaml") -> OrcSonarConfig:
    """Load and validate orcSONAR config from a YAML file.

    Args:
        path: Path to config.yaml (relative to CWD or absolute).

    Returns:
        Validated OrcSonarConfig instance.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.resolve()}")
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return OrcSonarConfig(**raw)


@lru_cache(maxsize=1)
def get_config(path: str = "config/config.yaml") -> OrcSonarConfig:
    """Cached singleton config loader. Safe to call repeatedly."""
    return load_config(path)
