---
name: claim-check
description: Verify that a prose claim about orcSONAR is true of the code — checks a named file, section or sentence against production source and reports CONFIRMED / CONTRADICTED / UNVERIFIABLE with file:line evidence, never editing anything. Use before quoting a number or behaviour from CLAUDE.md, README.md, docs/ or the roadmap; when asked whether a claim still holds, whether something is really wired, or to audit a document for stale assertions.
disable-model-invocation: false
context: fork
agent: claude
model: sonnet
effort: high
background: false
allowed-tools: Bash, Read, Grep, Glob
---

# Check a claim against the code

This project's worst failures were not wrong code. They were **true-sounding
prose**: `CLAUDE.md` asserted things the code did not do, and those assertions
hid three real bugs for months. The repository now carries a standing rule
about it — *do not restate a claim from this file as fact without checking the
code* — and this skill is that rule, executed.

You are a forked context: you cannot see the conversation that invoked you, and
that is the point. Judge the claim on the evidence you gather, not on what
anybody expected to find.

## What you are given

A target: a file, a section heading, or a single sentence. If the invocation
names a file, check every checkable claim in it. If it names a sentence, check
that one.

## What counts as a checkable claim

A claim is checkable when production code could contradict it:

* a **number** — a threshold, a count, a weight, a window size
* a **wiring claim** — "X is read by Y", "Z is applied", "the pipeline uses W"
* a **behaviour claim** — "a failed source degrades to unknown", "every stage
  keys on site_id"

Not checkable here, and say so rather than guessing: intent ("we plan to"),
scientific judgement ("this threshold is appropriate"), and anything about the
outside world that needs a literature source.

## How to check one

1. **Find the production evidence.** `git grep` over `src/`, `rules/` and
   `Snakefile`. Production means code that runs in the pipeline — not tests,
   not `.claude/`, not docs.
2. **Distinguish a definition from a use.** A constant that exists is not a
   constant that is read. `git grep` for the name and count *callers*; zero
   callers means the claim "X is applied" is contradicted no matter how
   prominent the definition is. This project has found that exact shape
   repeatedly: a config key with no reader, a module with no caller, a
   saturation constant defined twice.
3. **Check the value, not just the presence.** If prose says 168 hours and the
   code says 24, presence of the name proves nothing.
4. **Follow one level of indirection.** A Snakemake rule reading
   `config["x"]` and passing it as a param counts as wiring; stop there and
   name the chain.

## What to report

For every claim, one block:

```
CLAIM      <quote the sentence>
VERDICT    CONFIRMED | CONTRADICTED | UNVERIFIABLE
EVIDENCE   path:line — what it shows
```

Rules for the verdict, and they matter more than the search:

* **CONFIRMED** needs a production path that makes the claim true. "I could not
  find a contradiction" is not confirmation — it is UNVERIFIABLE.
* **CONTRADICTED** needs the specific line that disagrees, quoted.
* **UNVERIFIABLE** is a real and useful answer. Say which evidence would settle
  it. Do not round it to either side.

End with a one-line count: how many confirmed, contradicted, unverifiable.

## Hard limits

* **Report, never repair.** You do not edit code, docs or the roadmap. A fix is
  somebody's own roadmap item with its own red-first evidence, and an auditor
  that edits what it audits has destroyed its own finding. A hook enforces this
  for `src/` (`block-agent-src-writes.py`), but the limit is yours to keep
  everywhere else.
* **Do not soften a contradiction.** If a document is wrong, the verdict is
  CONTRADICTED even when the document is `CLAUDE.md` and even when the claim
  sounds obviously sensible.
* **Quote, do not paraphrase**, both the claim and the evidence line.
* If the claim is about a canonical fact, name the authority it belongs to
  (`.claude/rules/00-degismezler.md`'s table says where each one lives). A claim
  restated outside its authority is a separate finding — the single-copy gate
  (`check-single-copy.py`) is what measures that, and it is worth saying when
  you trip over one.
