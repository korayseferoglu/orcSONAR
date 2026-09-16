# orcSONAR — Project Guide for Claude Code

Cell-line-specific off-target risk predictor for saRNA (small activating RNA): merges
epigenetic, variant and thermodynamic evidence into a per-site risk score instead of
ranking by sequence similarity alone. Research prototype (ALPHA) — nothing validated.

## Stack
Python 3.11+ · Snakemake 9 · Pydantic v2 · loguru · pytest · YAML config · CLI only (no
web UI). The DAG is `Snakefile` + `rules/stage{1..7}.smk`; each rule's `run:` block calls
the `run()` of the matching `src/` module: read input JSON → compute → write
`results/{gene}_{cell_line}/stageN_*.json`. Most units are a pair — a Snakemake adapter
owning `run()` plus a pure-logic module with the tested functions.

## Current state — verify before trusting any claim
This file used to assert things the code does not do, and those claims hid real bugs for
months. Each row is an open finding with evidence in `AUDIT.md`; do not "fix" them in
passing, each is its own session's work.

| Area | What the code actually does | Target |
|---|---|---|
| Off-target search space (Bulgu-6) | `_BACKGROUND_GENES` in `src/stage2_offtarget_scan/transcriptome_fetcher.py` is a hand-curated **183-gene** set fetched over Ensembl REST. Not the transcriptome. | Full GENCODE scan (~250k transcripts) with a local seed index; thresholds must be recalibrated. |
| ΔG (Bulgu-1) | `src/stage5_biophysics/delta_g_calculator.py` uses the reverse complement of the saRNA **itself** as the duplex target, never the off-target mRNA. Every site in a run gets one identical, **positive** ΔG (+31.1 for VEGFA_HeLa) → `risk_score` 0.0 everywhere. The biophysics pillar is decorative. | Real per-site duplex ΔG. Blocked on stage 2: `stage2_offtargets.json` stores coordinates and `tx_start`/`tx_end`, not the sequence. |
| Cross-stage coordinates (Bulgu-2) | For the same site, stage 3 (COSMIC, phyloP) and stage 6 (Ago2) query a locus ~4 kb away from the stage 2 seed hit. | One region per off-target, shared by all stages. |

Two docstrings still claim "~250 genes" (`transcriptome_fetcher.py:133`,
`seed_aligner.py:311`) — also wrong; the list is 183. Coverage is uneven too: pure-logic
modules 95-100%, the `run()` adapters and mergers Snakemake actually calls 0% (Bulgu-3).

## Pipeline Stages (Dependency Order)
1 Genomic map (TSS from EPDnew + FANTOM5, transcript models → promoter window −1000 /
+200) → 2 Off-target scan (7-nt seed at positions 2-8 + miRBase + RepeatMasker) →
3 Variant/toxicity, 4 Epigenetic/topology, 5 Biophysics, 6 Execution/safety (these four
in parallel, all depending on `stage2_offtargets.json`) → 7 Scoring over the four merged
domain files → risk class → JSON/HTML report.

## Scoring Architecture
As implemented in `src/scoring/integrator.py` — all five domains enter `base_score`, and
`apply_cell_modifier` does **not** read `scoring_weights`:

```
base_score    = 0.20·sequence_specificity + 0.15·variant_toxicity
              + 0.25·biophysics_structure + 0.20·epigenetic_context
              + 0.20·execution_safety      # config/config.yaml, must sum to 1.0
cell_activity = 0.40·atac + 0.40·expression + 0.20·execution   # missing → 0.5
cell_modifier = 0.30 + 1.40·cell_activity                      # range [0.3, 1.7]
final_risk    = clamp(base_score × cell_modifier, 0, 1)

risk class: [0.0, 0.3) 🟢 SAFE · [0.3, 0.6) 🟡 WARNING ·
            [0.6, 0.8) 🟠 HIGH_RISK · [0.8, 1.0] 🔴 DANGEROUS
```

Known divergence — see AUDIT.md Bulgu-7. Note: epigenetic and execution signals enter
BOTH base_score and cell_modifier (double-counted); config weights do not mean what they
appear to mean. All four completed runs score 0.298-0.408, so HIGH_RISK and DANGEROUS are
never reached in practice — the dead ΔG pillar and frequent neutral fallbacks compress
the range (Bulgu-4).

## Key Design Decisions
- Off-target scanning: full transcript bodies, not just promoter regions — but currently
  only across the curated 183-gene background set (full GENCODE scan planned)
- Default test cell line: **HeLa**
- Supported cell lines: A549, GM12878, HEK293T, HeLa, HepG2, Huh7, K562, MCF7
- Score weights: Determine optimal weights based on literature
- All coordinates are hg38/GRCh38
- COSMIC VCF: NO "chr" prefix (1, 2, 3...)
- m6A BED: HAS "chr" prefix (chr1, chr2...)
- EPDnew/FANTOM5: HAS "chr" prefix

## Coding Standards
- Type hints on ALL functions
- Docstrings on ALL public functions (Google style)
- Pydantic v2 models for ALL data structures
- Use `loguru` for logging, NEVER `print()`
- Use `tenacity` for ALL API calls (retry with exponential backoff)
- Cache ALL API/BigWig results to `data/cache/` using SQLite
- Graceful degradation: if data source fails → log warning → use neutral score (0.5)
- Every module MUST have corresponding unit tests in `tests/unit/`
- Use `responses` library for mocking HTTP calls in tests

## File Naming Convention
- Source: `src/stageX_name/module_name.py`
- Tests: `tests/unit/test_module_name.py`
- Snakemake rules: `rules/stageX_name.smk`
- Results: `results/{gene}_{cell_line}/stageX_output.json`

## DO NOT
- Modify anything under `data/` (read-only)
- Use `print()` for logging (use loguru)
- Skip type hints or docstrings
- Skip unit tests
- Hardcode file paths (use config.yaml)
- Make API calls without retry/cache
- Load entire CCLE CSV into memory at once (use lazy loading)
- Restate a claim from this file as fact without checking the code

## Data sources
Paths, formats, column layouts, chr-prefix conventions and API endpoints for the 24
sources: `docs/DATA_SOURCES.md`, summarised by the `orcsonar-data-sources` skill.
Per-cell-line wiring: `config/cell_lines.yaml`, `config/ccle_depmap_ids.yaml`.
