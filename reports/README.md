# reports/ — agent reports

Where the review agents write, so a finding survives the session that produced it.
Before this directory existed the audit's three reports had to be hand-carried out of
the subagent transcripts; anything not relayed was lost.

`bio-reviewer`, `data-source-validator` and `literature-scout` have `Write` and drop
their output here as `<agent>_<subject>_<YYYY-MM-DD>.md` — for example
`bio-reviewer_seed-aligner_2026-11-17.md`.

## What a file here is, and is not

A report is **evidence**, not a verdict, and not a roadmap entry.

- Nothing here is acted on until a human reads it. An agent saying a line is wrong does
  not make it wrong; `AUDIT.md` and `SCIENTIFIC_ROADMAP.md` stay the authority on what
  is a real finding and what order it gets fixed in.
- Reports are **not gitignored on purpose.** A report shows up in `git status` and
  someone decides whether it is worth committing. Invariant 4 says uncommitted means
  nonexistent — so a finding that matters gets committed, and one that does not gets
  deleted rather than quietly accumulating.
- This directory is not pipeline output. `results/` is Snakemake's and nothing else
  writes there; see invariant 1.

⚠️ The "agents may only write **here**" rule is a **convention stated in each agent's
prompt, not an enforced one.** No hook restricts those three agents to this directory
today — `data/` and `results/` are guarded for every writer, but `src/` is not. See
`SCIENTIFIC_ROADMAP.md` H3.
