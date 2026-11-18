---
name: fix-done
description: Close an orcSONAR roadmap item — runs its acceptance script under .claude/acceptance/ and refuses the item if that script fails, and requires the red-first evidence invariant 5 demands. Use when work on a numbered SCIENTIFIC_ROADMAP.md item (H5, B2, C3, D1 …) looks finished, or when asked to mark an item done, close a finding, or verify an acceptance criterion.
disable-model-invocation: false
allowed-tools: Bash, Read, Edit
---

# Close a roadmap item

```bash
python3 .claude/skills/fix-done/scripts/fix_done.py <ID> \
    --red-first "<the test, and how it failed before the fix>" \
    [--declare "<what was observed>"]
```

Exit status: **0** the item may be closed, **1** refused, **2** the item or the
roadmap could not be read. If the acceptance script needs `pytest`, see
`.claude/acceptance/README.md` for the `PYTHON=` note.

## What it checks, and why each one is separate

**The red-first evidence (invariant 5).** Mandatory, always. A test that never
failed before the fix proves only that it does not fail now; it may be testing
a protection that does not exist. That happened here: the `curl`/`wget` hole
was found only because a red-first check showed the test passing against
nothing. If the item genuinely changed no code, say so with a reason —
`--red-first "yok: <reason>"` — and the exemption is recorded rather than
silent. No hook can measure this, which is why a skill asks.

**The acceptance criterion.** If `.claude/acceptance/<ID>.sh` exists, it runs
and a non-zero exit **refuses the item**, with the script's own output shown.
Prose does not override it; passing `--declare` alongside a gate is ignored.

If no gate exists, the criterion could not be made runnable — `H4`'s was "the
block prints at launch", observable only in a later session — so `--declare`
records what was observed and the verdict is `DONE(beyan)`: auditable, not
verified. **Never write an `exit 0` script to dodge this.** That makes the gate
lie, which is worse than having none.

## It does not write the roadmap

The verdict names the status cell to write. You then edit the row yourself,
because the part that matters is the prose next to it:

1. Put the status cell at the end of the row: `**DONE**` or `**DONE(beyan)**`.
2. In the same row, write what was measured — numbers, file:line, the
   red-first evidence. Future sessions trust this row instead of re-deriving
   it, so a vague row is worse than an empty one.
3. Anything you noticed but did not fix goes in as its **own row**
   (invariant 8), named, with evidence.
4. Commit. Invariant 4: uncommitted is nothing. The `h3k27me3 "wired ✅"` note
   existed in no commit, and the project believed it for months.

## It only closes an open item

`TODO` and `DOING` are the statuses it will act on. An item marked
`BLOCKED(...)` is refused, and that friction is deliberate: an item was blocked
for a reason, and clearing it should mean someone looked at whether the reason
still holds, not that a gate happened to pass.

So an unblocked item is moved back to `TODO` **by hand** first, in the same
edit that records why the block is gone. That happened to `H6b`: it was blocked
on a claim of mine that turned out to be wrong, and the block had to be
retracted in the row before the item could close.

## When it refuses

Then the item is not done. Do not loosen the acceptance script, lower a
threshold, or reach for `--declare` to get around a gate — invariant 7 names
threshold-lowering to compensate for dead channels as the most dangerous move
available in a risk tool. Fix the work, or change the roadmap row openly and
say why.
