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

**Start here: `SCIENTIFIC_ROADMAP.md`.** It is the ordered work queue — every open
finding as a numbered item with its dependency, a runnable acceptance criterion and a
status. Read its §2 invariants before changing anything, then take the first `TODO`
whose dependency is met and do only that one. The table below is a summary; the roadmap
is the authority on what to work on and in what order.

| Area | What the code actually does | Target |
|---|---|---|
| Off-target search space (Bulgu-6) | `_BACKGROUND_GENES` in `src/stage2_offtarget_scan/transcriptome_fetcher.py` is a hand-curated **183-gene** set fetched over Ensembl REST. Not the transcriptome. | Full GENCODE scan (~250k transcripts) with a local seed index; thresholds must be recalibrated. |
| ΔG (Bulgu-1) | `src/stage5_biophysics/delta_g_calculator.py` uses the reverse complement of the saRNA **itself** as the duplex target, never the off-target mRNA, **and** applies a stray `reversed()` on top. Every site in a run gets one identical, **positive** ΔG (+31.1 for VEGFA_HeLa) → `risk_score` 0.0 everywhere. The biophysics pillar is decorative. | Real per-site duplex ΔG — `SCIENTIFIC_ROADMAP.md` C3, fixed as a package (alignment + target + threshold together: correcting the alignment alone yields −43.8, which clears the `≤ −30` threshold and pins every site at 1.0). **NOT blocked on stage 2** — an earlier version of this row claimed it was; `tx_start`/`tx_end` *are* in the payload (`"tx_start": 7093, "tx_end": 7113`), so the target is sliced from the cached cDNA. Cleaner still: have stage 2 also emit the 20-nt `target_window` (~3 lines). |
| Genomic coordinates are splice-blind (Bulgu-8) | `seed_aligner.py:105-112` adds a **cDNA** offset (`transcriptome_fetcher.py:346` fetches `type="cdna"`) to a **genomic** span boundary, and `TranscriptInfo` carries no exon structure. Every site on a multi-exon transcript is placed wrongly: for MTOR only the top 8.7 kb of a 156 kb gene is reachable, so 94% of the locus can never be emitted. Affects every genomic-locus source (COSMIC, gnomAD, ClinVar, phyloP, ATAC, ChIP, GRO-seq, Hi-C, Ago2, RBP, m6A, circRNA, RepeatMasker); not SHAPE/ΔG/G4/miRBase/immune/CCLE. | Exon structure on `TranscriptInfo` (Ensembl `/lookup/id?expand=1`) and a cDNA→genomic walk over exons. |

Two docstrings still claim "~250 genes" (`transcriptome_fetcher.py:133`,
`seed_aligner.py:326`) — also wrong; the list is 183. Coverage is uneven too: pure-logic
modules 95-100%, the `run()` adapters and mergers Snakemake actually calls 0% (Bulgu-3).

**Fixed 2026-09-17 — Bulgu-2 (site identity).** A site is identified by
`OffTargetSite.site_id`, a `@computed_field` in `src/core/models.py`:
`gene:transcript:chrom:start`. Stage 2 emits it, every other stage keys on it
**verbatim** — never rebuild the string, that drift is what caused the bug. Field order
is load-bearing (`epigenetic_merger` takes field 0 as the gene, the HTML template field
1 as the transcript); `tests/unit/test_models.py::test_site_id_layout` pins it.
`score_integrator` raises if any stage carries a site id stage 2 did not emit. Verified:
VEGFA_HeLa 41 hits → 41 records in every stage, zero cross-stage coordinate divergence.
**Caveat: that means the stages now agree on a locus, not that the locus is right —
see Bulgu-8.**

The other three runs under `results/` (VEGFA_K562, CEBPA_HepG2, MYC_K562) predate this
and still carry two-part ids; re-run them before comparing against VEGFA_HeLa.

## Pipeline Stages (Dependency Order)
1 Genomic map (TSS from EPDnew + FANTOM5, transcript models → promoter window
−1000 / +200) → 2 Off-target scan (7-nt seed at positions 2-8 + miRBase + RepeatMasker) →
3 Variant/toxicity, 4 Epigenetic/topology, 5 Biophysics, 6 Execution/safety (these four
in parallel, all depending on `stage2_offtargets.json`) → 7 Scoring over the four merged
domain files → risk class → JSON/HTML report.

## Scoring
`base_score` is a weighted sum of five domains, scaled by a `cell_modifier` derived from
chromatin accessibility and expression; `final_risk = clamp(base × modifier, 0, 1)`.

The formula, the ways it diverges from what the weights suggest (double counting, the
constant-per-run modifier, which channels carry no information, why the top risk classes
are unreached) and the `site_id` contract are in
**`.claude/rules/20-skor-degismezleri.md`**, which loads automatically when you touch
`src/scoring/`, `src/stage7_*/` or `src/reporting/`. Do not restate those numbers here.

## Key Design Decisions
- Off-target scanning: full transcript bodies, not just promoter regions — but currently
  only across the curated 183-gene background set (full GENCODE scan planned)
- Default test cell line: **HeLa**
- Supported cell lines: see `config/cell_lines.yaml` — that file is the authority
- Score weights: `config/config.yaml`, but they are double-counted and not independently
  interpretable (rule 20)
- Coordinate bases, strand semantics, the seed slice and the hg38-everywhere rule:
  **`.claude/rules/10-koordinatlar.md`** (loads when you touch `src/`, `tests/` or
  `rules/*.smk`). Per-source chr-prefix and column layouts: `docs/DATA_SOURCES.md`.

## Coding Standards
- Type hints on ALL functions
- Docstrings on ALL public functions (Google style)
- Pydantic v2 models for ALL data structures
- Use `loguru` for logging, NEVER `print()`
- Use `tenacity` for ALL API calls (retry with exponential backoff)
- Cache ALL API/BigWig results to `data/cache/` using SQLite
- Graceful degradation: a failed source must never make a site look *safer*. What the
  code actually substitutes today, and why writing `0.5` would not fix it, is
  invariant 2 in `.claude/rules/00-degismezler.md`
- Every module MUST have corresponding unit tests in `tests/unit/`
- Use `responses` library for mocking HTTP calls in tests

## File Naming Convention
- Source: `src/stageX_name/module_name.py`
- Tests: `tests/unit/test_module_name.py`
- Snakemake rules: `rules/stageX_name.smk`
- Results: `results/{gene}_{cell_line}/stageX_output.json`

## DO NOT
The eight invariants live in `.claude/rules/00-degismezler.md`, which loads on every
session; the short version, plus the rules specific to this codebase:

- Modify anything under `data/` — read-only. Machine downloads go to `data/external/`
  with a manifest entry; that is the only writable path below `data/`
- Hand-edit anything under `results/` — only Snakemake writes there. Editing a result
  does not fix it, it fabricates one
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
