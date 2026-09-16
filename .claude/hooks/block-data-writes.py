#!/usr/bin/env python3
"""PreToolUse guard: refuse any Write/Edit/MultiEdit under data/.

data/ is read-only reference data (~1.5 GB): COSMIC VCF, CCLE/DepMap, m6A
BED, EPDnew, FANTOM5, miRBase, Turner rules, plus the SQLite API cache. Parts
of it are licence-gated and registration-walled, so an overwritten file is not
something a re-download can quietly restore.
"""

from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import block, read_payload, rel, target_path, under  # noqa: E402

payload = read_payload()
path = target_path(payload)

if path and under(path, "data"):
    block(
        f"BLOCKED: {rel(path)} is under data/, which is read-only.\n"
        "data/ holds ~1.5 GB of reference data, some of it licence-gated and not\n"
        "re-downloadable (COSMIC needs registration). Nothing in the pipeline may\n"
        "write here. Put derived files under results/ (via Snakemake) or a scratch\n"
        "directory instead."
    )
