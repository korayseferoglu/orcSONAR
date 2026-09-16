---
name: verify-run
description: Audit the scientific health of a completed orcSONAR run — metric degeneracy, physical plausibility, cross-stage coordinate agreement, neutral-fallback rate, and score dynamic range. Use when asked to verify, check, validate or sanity-check a run under results/, or after re-running a pipeline stage. Takes {gene}_{cell_line}, e.g. VEGFA_HeLa.
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
- Graceful degradation is projectwide: a failed data source logs a warning and
  substitutes a **neutral 0.5**. That is why a completely dead source produces
  plausible-looking output instead of an error.
- Risk classes: `[0, 0.3)` SAFE, `[0.3, 0.6)` WARNING, `[0.6, 0.8)` HIGH_RISK,
  `[0.8, 1.0]` DANGEROUS.
- `results/` and `data/` are **read-only** — this is an audit. Never edit a
  result to make a check pass. Hooks enforce this, and defeating them by
  another route would be fabricating data.

## The five checks

**1. DEGENERACY — does any metric actually vary across sites?**
Distinct-value count per metric per stage file. `distinct == 1` with more than
one site is a FAIL: that metric carries no information, whatever its value.
This is the highest-yield check in the file; run it first and read it first.

**2. PHYSICAL RANGE — are the values physically possible?**
Duplex **ΔG must be negative** (kcal/mol) — a positive ΔG means no duplex
formed, which is a bug, not a measurement. Normalised scores must be in
`[0, 1]`; conservation in `[0, 1]`; allele frequency in `[0, 1]`.

**3. COORDINATE CONSISTENCY — do the stages agree where each site is?**
Compares every downstream stage's recorded `region` against stage 2's **best**
seed hit (fewest mismatches) for that site. Reports, per file, how many
regions differ, the median and maximum offset in bp, and whether the stage
kept a worse-scoring duplicate or a locus stage 2 never reported at all. A
stage reading a locus kilobases from the actual off-target is measuring the
wrong piece of the genome.

**4. FALLBACK RATE — measured data, or the neutral sentinel?**
Per metric, how many sites sit at exactly `0.5`. A metric at 100% neutral is
decoration: the source failed and the pipeline substituted a number that looks
like a result. Advisory — it fails only above 50%.

**5. DYNAMIC RANGE — which risk classes can this run reach?**
min / median / max / span of the per-site final scores, the class histogram,
and which classes never trigger. A classifier whose top classes are
unreachable cannot warn anyone about anything.

## Reporting back

Lead with the verdict and the count (`3 of 5 checks failed`), then the
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

A finding **not** in that table is new — say so explicitly and loudly, with
the file and the numbers. Do not fix anything in the same turn: each of these
is its own piece of work, and CLAUDE.md asks that they not be fixed in
passing.
