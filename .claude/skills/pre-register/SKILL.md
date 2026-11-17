---
name: pre-register
description: Open orcSONAR's pre-registration (docs/PRE_REGISTRATION.md, roadmap A12) from a placeholder template, and refuse to reopen it once committed — invariant 6 locks the hypothesis, primary metric, thresholds, null model and stopping rule. Use before any Phase A evaluation work, or when asked to pre-register, lock a metric or threshold, record an analysis plan, or change something already pre-registered.
disable-model-invocation: false
allowed-tools: Bash, Read, Edit
---

# Pre-register before measuring

```bash
python3 .claude/skills/pre-register/scripts/pre_register.py          # open it
python3 .claude/skills/pre-register/scripts/pre_register.py --check  # lock state
```

Exit status: **0** written, or `--check` found no lock; **1** the file exists
or is locked; **2** the lock state could not be read, in which case nothing is
touched.

## The rule this enforces

Invariant 6: once `docs/PRE_REGISTRATION.md` is committed, it is **read-only
forever**. A change needs a new `docs/PRE_REGISTRATION_v2.md`, and the
publication reports **both**. Moving a metric or a threshold after seeing the
result is this project's most consequential violation precisely because it
leaves no trace anyone would notice — a small commit, three months later, in a
file nobody rereads.

The `H8` hook that will block edits to the committed file **does not exist
yet**. Until it does, this script and the people reading diffs are the whole
enforcement. Do not treat its refusal as a formality to work around.

## Filling it in

Every field ships as an angle-bracket placeholder, deliberately: a template
with a default threshold in it locks a number nobody chose. The fields that
cannot be revised later are the ones worth arguing about now — hypothesis,
**one** primary metric, the thresholds and why they are those, the null model
and its multiple-testing correction, the stopping rule, and what gets reported
if the hypothesis fails.

That last one is not a formality either. Invariant 7: a negative result is
accepted and has a publication path. Searching for a positive result by tuning
weights, thresholds or constants is a violation, and lowering a threshold to
compensate for a dead channel is the worst version of it.

## State of play before Phase A

Do not pre-register around known breakage — fix it or scope it out explicitly.
Roughly 1.5 of 5 scoring domains carry information today: the ΔG pillar emits
one identical positive value per run, `sequence_specificity` is clamped to a
constant, ClinVar is entirely dead, and the top two risk classes are
unreachable. `SCIENTIFIC_ROADMAP.md` and `AUDIT.md` have the evidence; a
pre-registration written over those is a locked plan to measure nothing.
