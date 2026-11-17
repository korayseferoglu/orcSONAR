# `data/external/` — machine-downloaded data

The one writable path below `data/`.

Everything else under `data/` is **hand-curated reference data**: ~1.5 GB, parts of it
licence-gated and not re-downloadable (COSMIC needs registration). An overwritten file
there is not something a re-download quietly restores, so the guards refuse every write
to it.

This directory is different. What lands here is **reproducibly re-downloadable from a
public URL**, and every artifact is recorded in `manifest.json` with the checksum that
makes it verifiable. The pipeline may therefore write here, and the guards
(`.claude/hooks/block-data-writes.py`, `.claude/hooks/block-bash-writes.py`) carve it
out explicitly.

## Why the split exists

The planned sandbox rule (`SCIENTIFIC_ROADMAP.md` H12) makes `data/` genuinely
unwritable rather than merely guarded. Without this carve-out, that rule would have to
be switched off the week the GENCODE download lands (`D0`) — and a rule that is declared
and then disabled is worse than no rule. It is also the exact failure this project keeps
hitting: a constant in a config file that nothing reads, a type checker declared but
never installed, a QA check counting a sentinel the code does not use.

So the decision is made **before** the rule and before the download, which is roadmap
item `H1`.

## What belongs here

| | here (`data/external/`) | not here (`data/`) |
|---|---|---|
| origin | downloaded from a public URL by a script | obtained by hand, registration, or licence |
| recoverable | yes — re-run the download | no, or only by repeating a manual process |
| recorded | `manifest.json` entry with sha256 | `docs/DATA_SOURCES.md` prose |
| examples | GENCODE GTF + transcript FASTA, phyloP BigWig snapshots, frozen API dumps (`G0`) | COSMIC VCF, CCLE CSV, m6A-Atlas BED, Turner rules, SHAPE-seq |

Derived files do **not** belong here. Pipeline output goes to `results/` via Snakemake;
scratch work goes outside the repo.

## `manifest.json`

One entry per artifact. `sha256` is what makes a run reproducible — the run manifest
(`H10`) copies these digests into each result directory, so a result can always be traced
to the exact bytes it was computed from.

```json
{
  "schema_version": 1,
  "artifacts": [
    {
      "name": "gencode.v48.annotation.gtf.gz",
      "source": "https://ftp.ebi.ac.uk/pub/databases/gencode/...",
      "release": "v48",
      "assembly": "GRCh38",
      "downloaded": "2026-11-20",
      "bytes": 1234567,
      "sha256": "…",
      "licence": "…",
      "used_by": ["D1", "C0", "D2"]
    }
  ]
}
```

`used_by` carries roadmap item ids, so it is answerable in one grep which work an
artifact underpins — and which artifacts a re-run of that item needs.

## Adding an artifact

1. Download into this directory.
2. Add its `manifest.json` entry, `sha256` included.
3. Note the source and its conventions (chr-prefix, coordinate base, assembly) in
   `docs/DATA_SOURCES.md` — that file stays the authority on *how to read* a source;
   this manifest records *which exact bytes* are on disk.

Never edit an artifact in place. Replace it and update the digest, so a stale checksum
is always a loud failure rather than a quiet one.
