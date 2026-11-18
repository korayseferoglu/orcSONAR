---
name: verify-run
description: Audit the scientific health of a completed orcSONAR run — metric degeneracy, physical plausibility, cross-stage coordinate agreement, neutral-fallback rate, score dynamic range, and raw-signal saturation headroom. Use when asked to verify, check, validate or sanity-check a run under results/, or after re-running a pipeline stage. Takes {gene}_{cell_line}, e.g. VEGFA_HeLa.
disable-model-invocation: false
allowed-tools: Bash, Read, Grep
---

# Verify an orcSONAR run

A green Snakemake exit says the code ran. It does not say the numbers mean
anything. This skill answers the question exit 0 cannot: **is this run
scientifically usable?**

Every finding it reports has been seen for real in this repo. The ΔG pillar
emitted one identical `+31.1` for every site in four consecutive runs and
nobody noticed for months, because the pipeline exited 0 every time. Check 1
below would have caught it on day one.

## Run it

```bash
python3 .claude/skills/verify-run/scripts/verify_run.py {gene}_{cell_line}
```

Add `--json` for machine-readable findings, `--results-dir` if the results
tree is not at `results/`. Exit status: **0** all checks pass, **1** at least
one failed, **2** the run could not be read.

If the user named no run, list `results/*/` and ask which one — or, if only
one exists, use it and say so.

## Project facts you need (this skill does not inherit CLAUDE.md)

- Genome build is **hg38/GRCh38** throughout.
- Site ids are `GENE:TRANSCRIPT:CHROM:START`, e.g.
  `MTOR:ENST00000361445:chr1:11255438` — defined once as a computed field on
  `OffTargetSite` (`src/core/models.py`) and stored in the stage-2 JSON. Runs
  made before that fix carry the old two-part `GENE:TRANSCRIPT` id.
- Stage 2 writes a **list** of seed hits and can record several for one
  transcript; stages 3–6 store dicts keyed by site id. While the id was only
  `gene:transcript` those hits collided and each stage kept a different one —
  the mechanism behind check 3 (AUDIT.md Bulgu-2).
- **Coordinates being consistent is not the same as being correct.** Check 3
  going green means the stages agree on a locus, not that the locus is right:
  the genomic coordinates are computed splice-blind (AUDIT.md Bulgu-8). Never
  report a green check 3 as biological accuracy.
- Graceful degradation changed with roadmap **B2**, and which contract a run
  followed decides how you read its zeros.
  - **Since B2:** an unread source is written as **`null`**. A raw `0.0` means
    the assay covered the locus and recorded nothing. `encode_reader` also
    separates "this contig is not in the file" (unknown — where a `chr` prefix
    mismatch lands) from "this contig is present and silent" (a real `0.0`).
    The mergers exclude an unknown channel and renormalise the remaining
    weights, so `normalized_score` is `null` only when nothing at all was
    measured.
  - **Before B2** — which includes **every run currently under `results/`** —
    production substituted `_NEUTRAL_SIGNAL = 0.0` in raw-signal space, reached
    from six modules (ATAC, the three histone marks, GRO-seq, Ago2, RBP).
    `0.5` means "unknown", `0.0` means "no signal", and for every one of these
    sources less signal reads as **lower** risk, so a failed source did not
    produce a neutral site — it produced one that looks safe (AUDIT.md
    Bulgu-10), which is why a wholly dead source yielded plausible output
    instead of an error.
  - The result JSON does not say which era it came from (`H10` adds a run
    manifest). **Check the run's git SHA before reading its zeros as
    measurements.** Check 4 counts nulls and zeros separately and says so.
  - Still open: `score_integrator._clamp(None)` yields `0.5` in *score* space,
    where that value is the documented "unknown". `B3` replaces it with a
    coverage threshold that refuses to score a site at all.
- Risk classes: `[0, 0.3)` SAFE, `[0.3, 0.6)` WARNING, `[0.6, 0.8)` HIGH_RISK,
  `[0.8, 1.0]` DANGEROUS.
- `results/` and `data/` are **read-only** — this is an audit. Never edit a
  result to make a check pass. Hooks enforce this, and defeating them by
  another route would be fabricating data.

## The six checks

**1. DEGENERACY — does any metric actually vary across sites?**
Distinct-value count per metric per stage file. `distinct == 1` with more than
one site is a FAIL: that metric carries no information, whatever its value.
This is the highest-yield check in the file; run it first and read it first.

**2. PHYSICAL RANGE — are the values physically possible?**
Duplex **ΔG must be negative** (kcal/mol) — a positive ΔG means no duplex
formed, which is a bug, not a measurement. Normalised scores must be in
`[0, 1]`; conservation in `[0, 1]`; allele frequency in `[0, 1]`.

The raw-signal fields in `stage4_epigenetic.json` — `atac_signal`,
`h3k4me3_signal`, `h3k27ac_signal`, `groseq_signal`, `hic_contact`,
`ccle_expression` — are **exempt from the `[0, 1]` rule, deliberately**. They
hold measured quantities in native units (fold-change, coverage, contact
frequency, log2(TPM+1)); normalisation happens in the consumers. An H3K4me3
fold-change of 24 is a strong promoter, not a bug. The check applies only
non-negativity to them, audits `normalized_score` instead, and prints which
fields it exempted so a silent skip cannot pass for a clean result. Saturation,
the failure mode that does apply to them, is check 6.

**3. COORDINATE CONSISTENCY — do the stages agree where each site is?**
Compares every downstream stage's recorded `region` against stage 2's **best**
seed hit (fewest mismatches) for that site. Reports, per file, how many
regions differ, the median and maximum offset in bp, and whether the stage
kept a worse-scoring duplicate or a locus stage 2 never reported at all. A
stage reading a locus kilobases from the actual off-target is measuring the
wrong piece of the genome.

**4. FALLBACK RATE — measured data, or a no-data sentinel?**
Per metric, how many sites sit at **either** sentinel: the documented score-space
`0.5`, and the raw-space `0.0` the code actually writes. A metric that is wholly
sentinel is decoration — the source failed and the pipeline substituted a number
that looks like a result. Advisory: it fails only above 50%.

Both are counted because counting only `0.5` made this check blind. A metric
sitting at 100% `0.0` produced no finding at all, and the run was reported as
carrying measured data everywhere — which is how the dead Ago2/RBP and ClinVar
channels passed check 4 in every previous run.

The `0.0` count is reported but deliberately **not attributed**: it is either a
failed source or a genuinely silent locus, and the result JSON cannot tell the
two apart. Separating them needs the per-site `provenance` field
(`SCIENTIFIC_ROADMAP.md` B3). Report the number and that limitation together —
do not call a raw `0.0` a measurement, and do not call it a failure either.

**5. DYNAMIC RANGE — which risk classes can this run reach?**
min / median / max / span of the per-site final scores, the class histogram,
and which classes never trigger. A classifier whose top classes are
unreachable cannot warn anyone about anything.

**6. SATURATION HEADROOM — does normalisation flatten the raw signals?**
Normalisation is a saturating ramp, `min(1, raw / SAT)`, so every site at or
above `SAT` maps to exactly 1.0 and can no longer be ranked against any other
saturated site. Per raw signal: how many sites are saturated, and `max/SAT`.
A few saturated sites are expected — the most active promoters really are the
most active. Past **50%** the constant is simply too low and the metric has
stopped separating anything; that fails.

The two consumers use **different constants for the same signals** —
`src/scoring/domain_scores.py:42-46` (feeds the risk score: ATAC 10, histone
15, GRO-seq 5, Hi-C 0.2, CCLE 6) and
`src/stage4_epigenetic/epigenetic_merger.py:15-20` (feeds `normalized_score`:
ATAC 50, histone 20, GRO-seq 10, Hi-C 1.0, CCLE 8). Both are reported,
because a signal that is healthy for `normalized_score` can still be flat by
the time it reaches the score that matters. Read `max/SAT` alongside the
percentage: CEBPA_HepG2's `hic_contact` reaches **16,226× SAT**, which says
the constant is wrong by orders of magnitude, not that the locus is hot.

## Reporting back

Lead with the verdict and the count (`3 of 6 checks failed`), then the
failures worst-first. For each, give the **number**, not an impression: "30/30
sites share one ΔG of +31.1", not "ΔG looks degenerate".

Separate what is newly broken from what is already known. These are open,
documented findings — report them as confirmations, not discoveries:

| Expect to see | Known as |
|---|---|
| ΔG identical across all sites, value `+31.1` | AUDIT.md Bulgu-1 |
| stages 3/6 ~4 kb from the stage-2 hit (MTOR: 4077 bp) — **only in runs made before the site_id fix** | AUDIT.md Bulgu-2 |
| all scores compressed into 0.30–0.41, top classes dead | AUDIT.md Bulgu-4 |
| large neutral-0.5 populations, e.g. SHAPE | AUDIT.md Bulgu-5 |
| ago2 / rbp `raw_signal` flat **0.0** where the cell line has no eCLIP (every line but K562 and HepG2) — missing data pushed toward SAFE, not neutral | AUDIT.md Bulgu-10 |
| `stage3_clinvar` all-zero in every run, including loci where ClinVar has hundreds of pathogenic variants | AUDIT.md Bulgu-11 |
| `stage6_immune` per-site table identical across all sites | AUDIT.md Bulgu-12 |
| `stage5_adar` `shape_used` False on every site while `stage5_shape.json` carries measured data | AUDIT.md Bulgu-13 |
| `stage5_m6a` all-zero — expected by chance at a 20 bp window, not evidence of anything | AUDIT.md Bulgu-14 |

A run whose `results/` directory is missing entirely (exit 2) is an aborted
run, not a passing one — `logs/TP53_K562/` exists with no `results/TP53_K562/`.

A finding **not** in that table is new — say so explicitly and loudly, with
the file and the numbers. Do not fix anything in the same turn: each of these
is its own piece of work, and CLAUDE.md asks that they not be fixed in
passing.
