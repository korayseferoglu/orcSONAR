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
| ΔG (Bulgu-1) | `src/stage5_biophysics/delta_g_calculator.py` uses the reverse complement of the saRNA **itself** as the duplex target, never the off-target mRNA. Every site in a run gets one identical, **positive** ΔG (+31.1 for VEGFA_HeLa) → `risk_score` 0.0 everywhere. The biophysics pillar is decorative. | Real per-site duplex ΔG. Blocked on stage 2: `stage2_offtargets.json` stores coordinates and `tx_start`/`tx_end`, not the sequence. |
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
- Score weights: config/config.yaml, but see Scoring Architecture — they are
  double-counted and not independently interpretable (AUDIT.md Bulgu-7)
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
- Graceful degradation: if data source fails → log warning → substitute a neutral
  score. **The intended value is 0.5 and the code does not do this** — production
  writes `_NEUTRAL_SIGNAL = 0.0` (`encode_reader.py:35`) in raw-signal space, which
  reads as *low risk* rather than *unknown*, so a failed source silently makes a
  site look safe (AUDIT.md Bulgu-10). `epigenetic_merger.py:12` defines
  `_NEUTRAL = 0.5` and nothing reads it. Do not restate 0.5 as the behaviour; the
  fix is `SCIENTIFIC_ROADMAP.md` B2/B3 and is its own session's work.
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
