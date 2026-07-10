# orcSONAR

**A cell-specific, biophysics-informed risk predictor for saRNA off-targets.**

orcSONAR estimates the off-target risk of a small activating RNA (saRNA) guide
strand in a chosen human cell line. Instead of ranking candidates by raw BLAST /
FASTA sequence similarity alone, it integrates five layers of evidence —
sequence specificity, variant toxicity, RNA biophysics, cell-line epigenetics,
and RISC-execution safety — into a single, interpretable risk score.

It is a research prototype and decision-support tool, not a clinically validated
predictor. Scores are intended to help prioritise and triage candidates, and
should be read alongside the per-stage evidence the pipeline emits.

- **Genome assembly:** hg38 / GRCh38 throughout
- **Supported cell lines:** A549, GM12878, HEK293T, HeLa, HepG2, Huh7, K562, MCF7
- **Default example run:** VEGFA in HeLa
- **Interface:** command line only (no web UI)

---

## Table of contents

- [How it works](#how-it-works)
- [Scoring](#scoring)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Output files](#output-files)
- [CLI reference](#cli-reference)
- [Data sources](#data-sources)
- [Coverage and limitations](#coverage-and-limitations)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [References](#references)
- [License](#license)

---

## How it works

orcSONAR is a seven-stage [Snakemake](https://snakemake.github.io/) pipeline.
Each stage writes structured JSON that the next stage consumes.

```
saRNA guide + gene + cell line
          │
          ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 1 · Genomic map                                    │
│  TSS (EPDnew + FANTOM5) → transcript models (Ensembl/     │
│  RefSeq) → promoter window (−1000 / +200 bp)              │
└─────────────────────────┬────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 2 · Off-target scan (whole transcriptome)          │
│  seed alignment → miRBase overlap → RepeatMasker →        │
│  merged off-target sites                                  │
└─────────────────────────┬────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  Stage 3     │ │  Stage 4     │ │  Stage 5             │
│  Variant &   │ │  Epigenetic  │ │  Biophysics &        │
│  toxicity    │ │  & topology  │ │  structure           │
│              │ │              │ │                      │
│  COSMIC      │ │  ATAC-seq    │ │  Turner ΔG           │
│  gnomAD      │ │  ChIP-seq    │ │  SHAPE reactivity    │
│  ClinVar     │ │  GRO-seq     │ │  m6A / ADAR          │
│  phyloP      │ │  Hi-C / CCLE │ │  G-quadruplex        │
└──────┬───────┘ └──────┬───────┘ └──────┬───────────────┘
       │                │                │
       │                │         ┌──────▼───────────────┐
       │                │         │  Stage 6             │
       │                │         │  Execution & safety  │
       │                │         │                      │
       │                │         │  Ago2 eCLIP          │
       │                │         │  RBP competition     │
       │                │         │  circRNA sponging    │
       │                │         │  immune motifs       │
       │                │         └──────┬───────────────┘
       └────────────────┼────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 7 · Scoring                                        │
│  integrate 5 domains → cell-specific modulation →         │
│  risk class → JSON + HTML report                          │
└──────────────────────────────────────────────────────────┘
```

Stages 3–6 depend only on the merged off-target set from Stage 2 and run in
parallel; Stage 7 waits for all of them.

For the full source registry, on-disk layout, file-format conventions, and
coordinate caveats, see [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

---

## Scoring

The scoring logic lives in `src/scoring/integrator.py`; weights and thresholds
come from `config/config.yaml`.

```
final_risk = clamp(base_score × cell_modifier, 0, 1)
```

**`base_score`** is the weighted sum of **all five** domain scores. The weights
are validated at runtime and must sum to exactly 1.0:

| Domain | Default weight | Inputs |
|--------|:--------------:|--------|
| `sequence_specificity` | 0.20 | seed match, miRNA overlap, repeats |
| `variant_toxicity`     | 0.15 | COSMIC, gnomAD, ClinVar, phyloP |
| `biophysics_structure` | 0.25 | ΔG, SHAPE, m6A, ADAR, G4 |
| `epigenetic_context`   | 0.20 | ATAC, ChIP, GRO-seq, Hi-C, CCLE |
| `execution_safety`     | 0.20 | Ago2, RBP, circRNA, immune motifs |

**`cell_modifier`** then rescales the base score by how transcriptionally active
the locus is in the chosen cell line:

```
cell_activity = 0.4 × atac + 0.4 × expression + 0.2 × execution
cell_modifier = 0.3 + 1.4 × cell_activity          # range [0.3, 1.7]
```

Missing inputs default to 0.5, so `cell_activity = 0.5` gives
`cell_modifier = 1.0` and leaves the base score untouched. A closed, unexpressed
locus shrinks the risk; an open, highly expressed one amplifies it.

**Risk classes** (thresholds from `config/config.yaml`):

| Range | Class |
|-------|-------|
| `[0.0, 0.3)` | 🟢 SAFE |
| `[0.3, 0.6)` | 🟡 WARNING |
| `[0.6, 0.8)` | 🟠 HIGH_RISK |
| `[0.8, 1.0]` | 🔴 DANGEROUS |

---

## Installation

Requirements:

- Python 3.11 or newer (the pinned environment is tested on **Python 3.12**)
- Roughly **1.5 GB** free disk for the reference data (see
  [Data sources](#data-sources); `data/` is not shipped with the repository)
- A C toolchain and `libcurl` development headers **if you need remote BigWig
  streaming** — see the note below

Dependency versions are pinned in both `pyproject.toml` and `envs/orcsonar.yaml`
to the tested set, so the two paths install the same packages.

### Option A — pip / venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # runtime + test/lint tools; drop [dev] for runtime only
```

### Option B — conda

```bash
conda env create -f envs/orcsonar.yaml
conda activate orcsonar
pip install -e . --no-deps   # register the CLI entry point
```

### Remote BigWig support (important)

Seven data sources (phyloP, ATAC-seq, ChIP-seq, GRO-seq, and the two eCLIP
tracks) are streamed at run time as remote BigWig files. The prebuilt `pyBigWig`
wheel is compiled **without** `libcurl`, so it can open local BigWigs but **not**
remote URLs. If your run touches any remote source, rebuild `pyBigWig` from
source against system `libcurl`:

```bash
# Debian/Ubuntu: install the dev headers first
sudo apt-get install -y libcurl4-openssl-dev zlib1g-dev

# then rebuild only pyBigWig from source (dependencies stay as wheels)
pip install --force-reinstall --no-binary pyBigWig "pyBigWig==0.3.25"
```

Verify remote access works:

```python
import pyBigWig
bw = pyBigWig.open("https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw")
print(bw.chroms().get("chr1"))   # → 248956422 if libcurl support is present
```

If you only run against local data, the wheel is sufficient and this step can be
skipped.

### Verify the install

```bash
orcsonar --help
python -m pytest -q      # 905 tests; uses mocked HTTP, no network needed
```

---

## Quick start

```bash
# Predict off-target risk for a VEGFA saRNA in HeLa cells
orcsonar \
  --gene VEGFA \
  --cell-line HeLa \
  --sarna-sequence GCAACCATAGCCTCGGCCGC

# Dry run: print the Snakemake execution plan without running it
orcsonar \
  --gene VEGFA \
  --cell-line HeLa \
  --sarna-sequence GCAACCATAGCCTCGGCCGC \
  --dry-run
```

Results are written to `results/<GENE>_<CELL_LINE>/` (see below).

`orcsonar` is a thin wrapper around Snakemake; the equivalent direct invocation
is:

```bash
snakemake results/VEGFA_HeLa/final_report.html --cores 4
```

---

## Output files

A completed run populates `results/<GENE>_<CELL_LINE>/`:

```
results/VEGFA_HeLa/
├── stage1_tss.json               # TSS coordinates (EPDnew + FANTOM5)
├── stage1_transcripts.json       # transcript models (Ensembl + RefSeq)
├── stage1_promoter.json          # promoter window (−1000 / +200)
├── stage2_seed_hits.json         # seed-alignment hits (whole transcriptome)
├── stage2_mirbase.json           # miRNA overlap
├── stage2_repeats.json           # RepeatMasker annotation
├── stage2_offtargets.json        # merged off-target sites
├── stage3_cosmic.json            # COSMIC somatic variants
├── stage3_gnomad.json            # gnomAD population variants
├── stage3_clinvar.json           # ClinVar pathogenicity
├── stage3_phylop.json            # phyloP conservation
├── stage3_variants.json          # merged variant toxicity
├── stage4_atac.json              # ATAC-seq accessibility
├── stage4_histones.json          # histone ChIP-seq (H3K4me3, H3K27ac, H3K27me3)
├── stage4_groseq.json            # GRO-seq / nascent transcription
├── stage4_hic.json               # Hi-C chromatin contacts
├── stage4_ccle.json              # CCLE expression
├── stage4_epigenetic.json        # merged epigenetic context
├── stage5_deltag.json            # Turner ΔG thermodynamics
├── stage5_shape.json             # SHAPE reactivity
├── stage5_m6a.json               # m6A modification sites
├── stage5_adar.json              # ADAR editing risk (Alu proxy)
├── stage5_g4.json                # G-quadruplex detection
├── stage5_biophysics.json        # merged biophysics
├── stage6_ago2.json              # Ago2 eCLIP loading
├── stage6_rbp.json               # RBP competition (hnRNPA1)
├── stage6_circrna.json           # circRNA sponge overlap
├── stage6_immune.json            # TLR7/TLR8 immune motifs
├── stage6_execution.json         # merged execution safety
├── stage7_scores.json            # integrated domain scores
├── stage7_classification.json    # per-site risk classes
├── final_report.json             # machine-readable report
└── final_report.html             # human-readable HTML report
```

The report generator produces JSON and HTML. `final_report.json` contains the
keys `sarna_input`, `offtarget_sites`, `domain_scores_per_site`,
`final_risk_score`, `risk_class`, `cell_line_context`, and `_metadata`.

---

## CLI reference

```
usage: orcsonar [-h] --gene SYMBOL --cell-line CELL_LINE
                --sarna-sequence SEQ
                [--config FILE] [--output-dir DIR]
                [--cores N] [--dry-run] [--quiet]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--gene` | — | HGNC gene symbol of the saRNA target (e.g. `VEGFA`, `TP53`) |
| `--cell-line` | — | One of the eight supported cell lines |
| `--sarna-sequence` | — | Guide strand (DNA or RNA; `T` is converted to `U`) |
| `--config` | `config/config.yaml` | Pipeline configuration file |
| `--output-dir` | `results` | Base output directory (results land in `<dir>/<gene>_<cell_line>/`) |
| `--cores` | `4` | CPU cores for Snakemake |
| `--dry-run` | off | Print the execution plan without running |
| `--quiet` | off | Suppress the progress bar |

The same interface is available as `python -m src.cli`.

---

## Data sources

orcSONAR integrates 24 data sources. Ten are local files, five are REST/GraphQL
APIs, seven are streamed remote BigWig / `.hic` files, and two are computed from
another source. Full details, formats, and coordinate conventions are in
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

| # | Source | Access | Stage |
|---|--------|--------|:-----:|
| 1 | EPDnew (TSS) | local BED | 1 |
| 2 | FANTOM5 CAGE peaks | local BED | 1 |
| 3 | GENCODE / Ensembl | REST API | 1 |
| 4 | NCBI RefSeq | REST API | 1 |
| 5 | miRBase (human miRNAs) | local FASTA | 2 |
| 6 | RepeatMasker (UCSC) | REST API | 2, 5 |
| 7 | COSMIC v103 | local VCF.gz (tabix) | 3 |
| 8 | gnomAD v4 | GraphQL API | 3 |
| 9 | NCBI ClinVar | REST API | 3 |
| 10 | UCSC phyloP 100-way | remote BigWig | 3 |
| 11 | GRO-seq / PRO-seq | remote BigWig | 4 |
| 12 | ENCODE ATAC-seq | remote BigWig | 4 |
| 13 | Hi-C (4DN) | remote `.hic` | 4 |
| 14 | ENCODE ChIP-seq | remote BigWig | 4 |
| 15 | CCLE / DepMap | local CSV | 4 |
| 16 | Turner rules (NNDB) | local text | 5 |
| 17 | SHAPE reactivity (icSHAPE) | local text | 5 |
| 18 | m6A-Atlas (formerly RMBase) | local BED.gz (tabix) | 5 |
| 19 | ADAR editing risk | computed (Alu proxy) | 5 |
| 20 | G-quadruplex | computed (regex) | 5 |
| 21 | ENCODE Ago2 eCLIP | remote BigWig | 6 |
| 22 | ENCODE hnRNPA1 eCLIP | remote BigWig | 6 |
| 23 | circAtlas 3.0 | local BED | 6 |
| 24 | Immune motifs | local text | 6 |

The `data/` tree (~1.5 GB) is not tracked by git and must be assembled locally.
COSMIC in particular requires registration and licence acceptance and cannot be
redistributed here. Remote sources need only network access. See
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md#8-obtaining-the-data).

---

## Coverage and limitations

orcSONAR is honest about being incomplete. Read a score as a **prior informed by
whatever data was available**, not as a measurement — especially for cell lines
with sparse coverage.

- **Graceful degradation.** Every source can fail independently (network
  timeout, missing local file, unmapped cell line). When one does, the affected
  sub-score falls back to a neutral **0.5**, a warning is logged, and the run
  continues. A report produced with several sources unavailable is closer to a
  prior than to a measurement. Inspect the per-stage `data_available` flags in
  the JSON before interpreting a score.

- **SHAPE reactivity exists for HeLa only** (icSHAPE, GSM4333258). The other
  seven `SHAPE_Seq/` directories are empty placeholders; for those cell lines
  Stage 5 reports `data_available: false` and uses the neutral fallback.

- **Uneven per-cell-line coverage.** HepG2 and K562 are complete. Huh7 is nearly
  empty (no ATAC, no histone ChIP, no GRO-seq, no Hi-C, no eCLIP). HEK293T lacks
  H3K27me3 and Hi-C; MCF7 lacks Hi-C. Ago2 and hnRNPA1 eCLIP exist only for
  HepG2 and K562. The full matrix is in
  [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md#7-per-cell-line-coverage).

- **Nascent transcription uses proxies.** ENCODE does not provide GRO-seq /
  PRO-seq for every line, so `config/cell_lines.yaml` substitutes, in order of
  preference, PRO-seq → PRO-cap → GRO-cap → **CAGE** (HeLa-S3, HepG2, MCF-7).
  CAGE measures 5′ nascent TSS usage and is a proxy, not an equivalent.

- **Not clinically validated.** orcSONAR has not been benchmarked against
  experimental off-target measurements. Treat its output as a hypothesis-ranking
  aid, not ground truth.

---

## Running the tests

```bash
python -m pytest -q                       # full suite (905 tests)
python -m pytest tests/unit/ -v           # unit tests only
python -m pytest --cov=src --cov-report=html   # with coverage report
```

HTTP calls are mocked with the [`responses`](https://github.com/getsentry/responses)
library, so the suite runs offline and needs no reference data.

---

## Project structure

```
orcSONAR/
├── config/
│   ├── config.yaml              # main pipeline configuration
│   └── cell_lines.yaml          # per-cell-line remote-source accessions
├── data/                        # reference data (read-only, not tracked)
│   ├── 1_Temel_Harita/          # EPDnew, FANTOM5, miRBase
│   ├── 2_Varyant_Toksisite/     # COSMIC, phyloP
│   ├── 3_Topoloji_Epigenetik/   # CCLE expression matrix
│   ├── 4_Biyofizik_Yapısal/     # Turner rules, SHAPE, m6A
│   └── 5_Icra_Güvenlik/         # immune motifs, circAtlas
├── docs/
│   └── DATA_SOURCES.md          # full data-source reference
├── envs/
│   └── orcsonar.yaml            # conda environment spec
├── rules/                       # Snakemake rules, one per stage
│   ├── stage1_genomic.smk … stage7_scoring.smk
├── src/                         # Python modules
│   ├── cli.py                   # command-line interface
│   ├── core/                    # config, Pydantic models, cache
│   ├── stage1_genomic_map/ … stage6_execution/
│   ├── scoring/                 # integrator + risk classifier
│   └── reporting/               # JSON + HTML report generation
├── tests/
│   ├── unit/                    # per-module unit tests
│   └── integration/             # end-to-end pipeline tests
├── Snakefile                    # Snakemake entry point
├── pyproject.toml
└── README.md
```

Directory names under `data/` are Turkish and load-bearing — they appear
verbatim in `config/config.yaml`, so renaming one requires updating the config.

---

## References

Primary references for the integrated data sources:

- **EPDnew** — Meylan P, *et al.* EPD in 2020: enhanced data visualization and extension to ncRNA promoters. *Nucleic Acids Res* 48(D1):D65–D69 (2020). [doi:10.1093/nar/gkz1014](https://doi.org/10.1093/nar/gkz1014)
- **FANTOM5** — Lizio M, *et al.* Gateways to the FANTOM5 promoter level mammalian expression atlas. *Genome Biol* 16:22 (2015). [doi:10.1186/s13059-014-0560-6](https://doi.org/10.1186/s13059-014-0560-6)
- **miRBase** — Kozomara A, Birgaoanu M, Griffiths-Jones S. miRBase: from microRNA sequences to function. *Nucleic Acids Res* 47(D1):D155–D162 (2019). [doi:10.1093/nar/gky1141](https://doi.org/10.1093/nar/gky1141)
- **COSMIC** — Tate JG, *et al.* COSMIC: the Catalogue Of Somatic Mutations In Cancer. *Nucleic Acids Res* 47(D1):D941–D947 (2019). [doi:10.1093/nar/gky1015](https://doi.org/10.1093/nar/gky1015)
- **gnomAD v4** — Chen S, *et al.* A genomic mutational constraint map using variation in 76,156 human genomes. *Nature* 625:92–100 (2024). [doi:10.1038/s41586-023-06045-0](https://doi.org/10.1038/s41586-023-06045-0)
- **ClinVar** — Landrum MJ, *et al.* ClinVar: improving access to variant interpretations and supporting evidence. *Nucleic Acids Res* 46(D1):D1062–D1067 (2018). [doi:10.1093/nar/gkx1153](https://doi.org/10.1093/nar/gkx1153)
- **phyloP / PHAST** — Pollard KS, *et al.* Detection of nonneutral substitution rates on mammalian phylogenies. *Genome Res* 20(1):110–121 (2010). [doi:10.1101/gr.097857.109](https://doi.org/10.1101/gr.097857.109)
- **CCLE / DepMap** — Ghandi M, *et al.* Next-generation characterization of the Cancer Cell Line Encyclopedia. *Nature* 569:503–508 (2019). [doi:10.1038/s41586-019-1186-3](https://doi.org/10.1038/s41586-019-1186-3)
- **ENCODE** — ENCODE Project Consortium. Expanded encyclopaedias of DNA elements in the human and mouse genomes. *Nature* 583:699–710 (2020). [doi:10.1038/s41586-020-2493-4](https://doi.org/10.1038/s41586-020-2493-4)
- **Turner rules (NNDB)** — Turner DH, Mathews DH. NNDB: the nearest neighbor parameter database for predicting stability of nucleic acid secondary structure. *Nucleic Acids Res* 38(suppl_1):D280–D282 (2010). [doi:10.1093/nar/gkp892](https://doi.org/10.1093/nar/gkp892)
- **icSHAPE** — Flynn RA, *et al.* Transcriptome-wide interrogation of RNA secondary structure in living cells with icSHAPE. *Nat Protoc* 11(2):273–290 (2016). [doi:10.1038/nprot.2016.011](https://doi.org/10.1038/nprot.2016.011)
- **m6A-Atlas** — Tang Y, *et al.* m6A-Atlas: a comprehensive knowledgebase for unraveling the N6-methyladenosine (m6A) epitranscriptome. *Nucleic Acids Res* 49(D1):D134–D143 (2021). [doi:10.1093/nar/gkaa692](https://doi.org/10.1093/nar/gkaa692)
- **circAtlas 3.0** — Wu W, Zhao F, Zhang J. circAtlas 3.0: a gateway to 3 million curated vertebrate circular RNAs based on a standardized nomenclature scheme. *Nucleic Acids Res* 52(D1):D52–D60 (2024). [doi:10.1093/nar/gkad770](https://doi.org/10.1093/nar/gkad770)

Additional portals: [Ensembl](https://rest.ensembl.org), [NCBI E-utilities](https://eutils.ncbi.nlm.nih.gov/), [UCSC Genome Browser](https://genome.ucsc.edu/), [ENCODE portal](https://www.encodeproject.org/), and the [4D Nucleome Data Portal](https://data.4dnucleome.org/).

---

## License

Released under the [MIT License](LICENSE). Copyright © 2026 Enes Koray Seferoglu.

Note: the licence covers orcSONAR's source code only. The third-party datasets it
consumes carry their own licences and terms — most notably COSMIC, which requires
registration and a separate licence for commercial use.
