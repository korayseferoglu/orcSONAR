---
name: next-fix
description: Pick the one orcSONAR roadmap item a session may work on next — the first TODO in SCIENTIFIC_ROADMAP.md whose dependencies are all closed — with its full work text, acceptance criterion and whether a machine-checkable gate exists for it. Use at the start of a session, or when asked what to work on, what is next, which finding to fix, or whether an item is unblocked.
disable-model-invocation: false
allowed-tools: Bash, Read
---

# What to work on next

`SCIENTIFIC_ROADMAP.md` is the authority on what gets done and in what order.
This skill reads it and answers one question: **which item may be started now.**

```bash
python3 .claude/skills/next-fix/scripts/next_fix.py
```

Add `--json` for the raw fields. Exit status: **0** an item was printed, **1**
nothing is ready, **2** the roadmap could not be read.

The parser is `.claude/hooks/_status.py` — the same one the launch status block
uses. Do not write a second roadmap parser anywhere; divergence between two
copies of a fact is the failure mode roadmap `H9` exists to close.

## Then do only that item

Invariant 8: **one item is one piece of work.** Nothing you notice on the way
gets fixed in passing — it goes into the roadmap as its own row and stays
there. This is not tidiness. A commit that fixes the item plus three things
nearby cannot be reverted when one of the four turns out to be wrong, and in a
risk tool the fourth one is the one that matters.

## Read before touching anything

- `.claude/rules/00-degismezler.md` loads every session; §2 of the roadmap has
  the reasoning behind each invariant.
- Rules with a `paths:` header load when you touch the files they cover
  (`10-koordinatlar.md` for coordinates and strand, `20-skor-degismezleri.md`
  for scoring). They are not optional reading, they are just late.
- The claims in `CLAUDE.md` are **not** evidence. That file asserted things the
  code did not do for months, and those assertions hid three real bugs. Check
  the code.

## Before you call it done

The acceptance line this skill prints is what `fix-done <ID>` will check. The
`kapı` line tells you which closure is available:

- a gate exists → closing is verified against it; a non-zero exit refuses the
  item and no argument gets past that,
- no gate → write one if the criterion can be expressed as a command, because
  the alternative closure (`DONE(beyan)`) is permanently weaker in the table.

Either way, have the **red-first** evidence ready: the test that catches the
bug, shown failing *before* the fix. `fix-done` will not close an item without
it, and no hook can measure it for you (invariant 5). 917 tests were green in
this repo while all three known bugs were live.
