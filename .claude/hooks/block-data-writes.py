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

from _hooklib import (  # noqa: E402
    DATA_EXTERNAL,
    block,
    is_writable_data,
    read_payload,
    rel,
    target_path,
    under,
)

payload = read_payload()
path = target_path(payload)

if path and under(path, "data") and not is_writable_data(path):
    block(
        f"BLOCKED: {rel(path)} is under data/, which is read-only.\n"
        "data/ holds ~1.5 GB of hand-curated reference data, some of it\n"
        "licence-gated and not re-downloadable (COSMIC needs registration).\n"
        "Nothing in the pipeline may write here.\n\n"
        f"The one exception is {DATA_EXTERNAL}/ — machine-downloaded data (GENCODE\n"
        "and friends) belongs there, recorded in its manifest.json. Otherwise put\n"
        "derived files under results/ (via Snakemake) or a scratch directory."
    )
