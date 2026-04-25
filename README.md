# orcSONAR

**World's first cell-specific, biophysics-driven saRNA off-target predictor.**

Replaces BLAST/FASTA sequence similarity with an integrative decision-support system combining epigenetics, variant data (COSMIC), and thermodynamic parameters to predict off-target risk for small activating RNAs (saRNAs) at single-nucleotide resolution.

---

## Installation

### Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- ~15 GB free disk space (for reference data)

### Create the environment

```bash
conda env create -f envs/orcsonar.yaml
conda activate orcsonar
```

### Verify

```bash
python -m pytest tests/unit/ -q
# Expected: all unit tests pass
```

---

## Quick Start

```bash
conda activate orcsonar

# Predict off-target risk for VEGFA saRNA in HeLa cells
python -m src.cli \
  --gene VEGFA \
  --cell-line HeLa \
  --sarna-sequence GCAACCATAGCCTCGGCCGC \
  --output-dir results/VEGFA_HeLa

# Dry-run (shows Snakemake DAG without executing)
python -m src.cli \
  --gene VEGFA \
  --cell-line HeLa \
  --sarna-sequence GCAACCATAGCCTCGGCCGC \
  --dry-run
```

### Output

```
results/VEGFA_HeLa/
├── stage1_tss.json          # TSS coordinates (EPDnew + FANTOM5)
├── stage1_transcripts.json  # Transcript models (Ensembl + NCBI)
├── stage1_promoter.json     # Promoter window (-1000/+200)
├── stage2_seed_hits.json    # Seed alignment hits (whole transcriptome)
├── stage2_mirbase.json      # miRNA overlap
├── stage2_repeats.json      # RepeatMasker results
├── stage2_offtargets.json   # Merged off-target sites
├── stage3_cosmic.json       # COSMIC somatic variants
├── stage3_gnomad.json       # gnomAD population variants
├── stage3_clinvar.json      # ClinVar pathogenicity
├── stage3_phylop.json       # PhyloP conservation scores
├── stage3_variants.json     # Merged variant toxicity
├── stage4_atac.json         # ATAC-seq chromatin accessibility
├── stage4_histone.json      # H3K4me3 + H3K27ac signals
├── stage4_groseq.json       # GRO-seq transcription
├── stage4_hic.json          # Hi-C chromatin contacts
├── stage4_ccle.json         # CCLE gene expression
├── stage4_epigenetic.json   # Merged epigenetic context
├── stage5_deltag.json       # Turner ΔG thermodynamics
├── stage5_shape.json        # SHAPE-seq accessibility
├── stage5_m6a.json          # m6A modification sites
├── stage5_adar.json         # ADAR editing risk (Alu proxy)
├── stage5_g4.json           # G-quadruplex detection
├── stage5_biophysics.json   # Merged biophysics
├── stage6_ago2.json         # Ago2 eCLIP loading
├── stage6_rbp.json          # RBP competition (hnRNPA1)
├── stage6_circrna.json      # circRNA sponge overlap
├── stage6_immune.json       # TLR7/TLR8 immune motifs
├── stage6_execution.json    # Merged execution safety
├── stage7_scores.json       # Final integrative scores
├── final_report.json        # Machine-readable report
└── final_report.html        # Human-readable HTML report
```

---

## CLI Reference

```
usage: python -m src.cli [-h] --gene GENE --cell-line CELL_LINE
                         --sarna-sequence SARNA_SEQUENCE
                         [--config CONFIG] [--output-dir OUTPUT_DIR]
                         [--cores CORES] [--dry-run] [--quiet]

Options:
  --gene              Target gene symbol (e.g. VEGFA, TP53, BRCA1)
  --cell-line         Cell line context: A549, GM12878, HEK293T, HeLa,
                      HepG2, Huh7, K562, MCF7
  --sarna-sequence    saRNA guide strand (10–30 nt, DNA or RNA; T→U auto-converted)
  --config            Path to config.yaml (default: config/config.yaml)
  --output-dir        Results directory (default: results/{gene}_{cell_line})
  --cores             CPU cores for Snakemake (default: 4)
  --dry-run           Print the execution plan without running
  --quiet             Suppress progress bar
```

### Examples

```bash
# TP53 in K562 (leukemia) cells
python -m src.cli --gene TP53 --cell-line K562 \
  --sarna-sequence AGACUCUGAGUCAGGAGAUG

# BRCA1 with custom config and 8 cores
python -m src.cli --gene BRCA1 --cell-line MCF7 \
  --sarna-sequence GCAACCAUAGCCUCGGCCGC \
  --config config/config_hpc.yaml --cores 8

# Snakemake direct (equivalent to CLI)
snakemake results/VEGFA_HeLa/final_report.html --cores 4
```

---

## Architecture

orcSONAR is a 7-stage Snakemake pipeline. Each stage outputs structured JSON consumed by the next.

```
saRNA sequence + gene + cell line
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Genomic Map                                   │
│  TSS (EPDnew + FANTOM5) → Transcripts (Ensembl/NCBI)   │
│  → Promoter window (-1000/+200 bp)                      │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2: Off-Target Scan (Whole Transcriptome)         │
│  Seed alignment → miRNA overlap (miRBase)               │
│  → RepeatMasker → Merged off-target sites               │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  Stage 3     │ │  Stage 4     │ │  Stage 5             │
│  Variant &   │ │  Epigenetic  │ │  Biophysics          │
│  Toxicity    │ │  & Topology  │ │  & Structural        │
│              │ │              │ │                      │
│  COSMIC      │ │  ATAC-seq    │ │  Turner ΔG           │
│  gnomAD      │ │  ChIP-seq    │ │  SHAPE-seq           │
│  ClinVar     │ │  GRO-seq     │ │  m6A / ADAR          │
│  phyloP      │ │  Hi-C / CCLE │ │  G-quadruplex        │
└──────┬───────┘ └──────┬───────┘ └──────┬───────────────┘
       │                │                │
       │                │         ┌──────▼───────────────┐
       │                │         │  Stage 6             │
       │                │         │  Execution & Safety  │
       │                │         │                      │
       │                │         │  Ago2 eCLIP          │
       │                │         │  RBP competition     │
       │                │         │  circRNA sponge      │
       │                │         │  Immune motifs       │
       │                │         └──────┬───────────────┘
       └────────────────┼────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 7: Scoring Engine                                │
│  Multi-domain integration → Risk classification        │
│  → JSON + HTML + PDF reports                           │
└─────────────────────────────────────────────────────────┘
```

### Scoring Formula

```
Final Risk = Base_Score × Cell_Modifier

Base_Score = weighted sum of 5 domain scores:
  • Sequence Specificity  (0.20) — seed match, miRNA overlap, repeats
  • Variant Toxicity      (0.15) — COSMIC, gnomAD, ClinVar, phyloP
  • Biophysics Structure  (0.25) — ΔG, SHAPE, m6A, ADAR, G4

Cell_Modifier derived from:
  • Epigenetic Context    (0.20) — ATAC, ChIP, GRO-seq, Hi-C, CCLE
  • Execution Safety      (0.20) — Ago2, RBP, circRNA, immune

Risk Classification:
  [0.0, 0.3)  →  SAFE
  [0.3, 0.6)  →  WARNING
  [0.6, 0.8)  →  HIGH_RISK
  [0.8, 1.0]  →  DANGEROUS
```

---

## Data Sources

| # | Source | Access | Format | Stage |
|---|--------|--------|--------|-------|
| 1 | EPDnew (TSS database) | Local BED | BED6+ | 1 |
| 2 | FANTOM5 CAGE peaks | Local BED | BED9 | 1 |
| 3 | GENCODE / Ensembl REST | REST API | JSON | 1 |
| 4 | NCBI RefSeq | REST API | XML/JSON | 1 |
| 5 | miRBase (human miRNAs) | Local FASTA | FASTA | 2 |
| 6 | RepeatMasker (UCSC) | REST API | JSON | 2, 5 |
| 7 | COSMIC v103 | Local VCF.gz (Tabix) | VCF | 3 |
| 8 | gnomAD v4 | GraphQL API | JSON | 3 |
| 9 | NCBI ClinVar | REST API | XML | 3 |
| 10 | UCSC phyloP 100way | Remote BigWig | BigWig | 3 |
| 11 | GRO-Seq / PRO-Seq | Remote BigWig | BigWig | 4 |
| 12 | ENCODE ATAC-Seq | Remote BigWig | BigWig | 4 |
| 13 | Hi-C / 4DN | Remote .hic | .hic | 4 |
| 14 | ENCODE ChIP-Seq | Remote BigWig | BigWig | 4 |
| 15 | CCLE / DepMap | Local CSV | CSV | 4 |
| 16 | Turner thermodynamic rules | Local .dg/.dat | Custom | 5 |
| 17 | SHAPE-Seq (8 cell lines) | Local .shape/.map | Text | 5 |
| 18 | m6A-Atlas (RMBase) | Local BED.gz (Tabix) | BED | 5 |
| 19 | REDIportal (ADAR) | Computed via Alu proxy | — | 5 |
| 20 | G4RNA | Local regex algorithm | — | 5 |
| 21 | ENCODE Ago2 eCLIP | Remote BigWig | BigWig | 6 |
| 22 | POSTAR3 / ENCODE eCLIP (hnRNPA1) | Remote BigWig | BigWig | 6 |
| 23 | circAtlas 3.0 | Local BED (reserved) | BED | 6 |
| 24 | Immune motif database | Local text | Plain text | 6 |

**Supported cell lines**: A549, GM12878, HEK293T, HeLa, HepG2, Huh7, K562, MCF7

**Genome assembly**: hg38 / GRCh38

---

## Running the Tests

```bash
conda activate orcsonar

# Unit tests (fast, no network/data required)
python -m pytest tests/unit/ -v

# Integration tests (Stage 7 scoring + report generation)
python -m pytest tests/integration/ -v

# Full test suite with coverage
python -m pytest --cov=src --cov-report=html
open htmlcov/index.html
```

---

## Project Structure

```
orcSONAR/
├── config/
│   └── config.yaml              # Main pipeline configuration
├── data/                        # Reference data (read-only)
│   ├── 1_Temel_Harita/          # EPDnew, FANTOM5, miRBase
│   ├── 2_Varyant_Toksisite/     # COSMIC, phyloP
│   ├── 3_Topoloji_Epigenetik/   # CCLE expression matrix
│   ├── 4_Biyofizik_Yapısal/     # Turner rules, SHAPE-seq, m6A
│   └── 5_Icra_Güvenlik/         # Immune motifs, circAtlas
├── envs/
│   └── orcsonar.yaml            # Conda environment spec
├── rules/                       # Snakemake rules (one per stage)
│   ├── stage1_genomic.smk
│   ├── stage2_offtarget.smk
│   ├── stage3_variant.smk
│   ├── stage4_epigenetic.smk
│   ├── stage5_biophysics.smk
│   ├── stage6_execution.smk
│   └── stage7_scoring.smk
├── src/                         # Python source modules
│   ├── cli.py                   # Command-line interface
│   ├── core/                    # Config, models, cache
│   ├── stage1_genomic_map/
│   ├── stage2_offtarget_scan/
│   ├── stage3_variant_tox/
│   ├── stage4_epigenetic/
│   ├── stage5_biophysics/
│   ├── stage6_execution/
│   ├── scoring/                 # Score integrator + classifier
│   └── reporting/               # JSON + HTML + PDF report generation
├── tests/
│   ├── unit/                    # Per-module unit tests
│   └── integration/             # End-to-end pipeline tests
├── Snakefile                    # Snakemake entry point
└── README.md
```

---

## Graceful Degradation

orcSONAR is designed to always complete, even when data sources are unavailable:

- **API timeout / network failure** → neutral score (0.5), warning logged
- **Missing SHAPE-seq data** → `accessibility_score=0.5, data_available=False`
- **No circRNA BED file** → `sponge_risk=False, data_available=False`
- **No COSMIC variants in region** → `density_score=0.0`
- **Remote BigWig unreachable** → signal=0.0, score uses neutral fallback

All fallbacks are logged via `loguru` at WARNING level. The final report includes a `data_availability` section indicating which sources were successfully queried.

---

## Citation

If you use orcSONAR in your research, please cite: *(manuscript in preparation)*
