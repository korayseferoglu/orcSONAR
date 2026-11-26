---
name: null-check
description: Run orcSONAR's empirical 7-mer null for the off-target seed — counts all 16384 possible 7-mers against the same background the pipeline scans and reports where the real seed ranks, with a one-sided empirical p-value, into reports/null_gate.json. Use when asked whether the off-target hits are enriched over chance, to run or re-run the null model or null gate, before interpreting a hit count, or when roadmap E1 or H13 comes up.
disable-model-invocation: false
allowed-tools: Bash, Read
---

# The null the hit list has to beat

A run reporting 41 off-target sites reads as alarming. The question that makes
it meaningful is the one nobody asks on their own: **how many would an
arbitrary 7-mer have hit against the same background?**

```bash
~/.venvs/orcsonar/bin/python .claude/skills/null-check/scripts/null_check.py
```

Writes `reports/null_gate.json`. The `H4` status line reads
`reports/null_gate*.json` at launch and prints the last result, so writing it
anywhere else leaves the status line saying "never ran" (roadmap `E1`).

## What it computes, and why it is exact

There are 4^7 = 16384 possible 7-mers, so there is no reason to sample: every
one is counted against the background and the observed seed's rank is read
straight off the distribution. No resampling, no distributional assumption, no
tuning knob.

Two units, because conflating them is easy and they answer different questions:

| unit | question |
|---|---|
| `transcripts` | in how many background transcripts does the seed's match site appear at all — the candidacy step |
| `occurrences` | how many match positions exist in total, since one transcript can carry several |

The matching rule is the pipeline's own: `reverse_complement(seed)` searched in
cDNA space, seed taken from guide positions 2-8 (`.claude/rules/10-koordinatlar.md`).
Using a different rule for the null than for the observation would compare two
different experiments, which is the most common way a null model flatters its
hypothesis.

k-mers absent from the background are counted as **zero rather than dropped**.
Excluding them would compare the observed seed only against seeds that happen
to occur — the easier comparison, and the wrong one.

## What it deliberately does not do

It computes no threshold and prints no verdict. Choosing a cutoff after seeing
the distribution is invariant 7's violation, and the cutoff belongs in
`docs/PRE_REGISTRATION.md` (roadmap `A12`). The script measures; interpretation
is a separate, pre-registered step.

It also does not touch `results/`. The report is provenance-free evidence about
the *background*, not about any one run.

## Reading the output

`percentile_of_observed` is where the real seed sits among all 16384.
`p_empirical_ge` is the fraction of 7-mers at least as promiscuous as this one
— one-sided and inclusive of the observation.

A percentile near 50 means the seed is ordinary. That is a result, not a
failure: invariant 7 says a negative result is acceptable and has a publication
path. The danger is the opposite reading — treating a long hit list as evidence
of risk when an arbitrary seed would have produced a similar one.

## Before quoting a number from it

Check `background.sequences_non_empty` and `background.resolution_coverage` in
the report. A null built on a partly-resolved background is a null for a
different background: roadmap `R12a` found the set had been only 12% resolved
while the run said nothing about it, and the measured counts moved once that
was fixed. A null whose background differs from the run's background cannot
score that run.
