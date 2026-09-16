#!/usr/bin/env python3
"""PreToolUse guard: refuse any Write/Edit/MultiEdit under results/.

The JSON under results/ is measurement output — what the pipeline computed for
a given gene and cell line. Editing it by hand does not fix a result, it
fabricates one, and the fabrication is indistinguishable from a real run
afterwards. Snakemake is the only legitimate writer.
"""

from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import block, read_payload, rel, target_path, under  # noqa: E402

payload = read_payload()
path = target_path(payload)

if path and under(path, "results"):
    block(
        f"BLOCKED: {rel(path)} is under results/, which only Snakemake may write.\n"
        "These files are pipeline measurements. Hand-editing one manufactures data\n"
        "that later reads as a genuine run — there is no way to tell afterwards.\n"
        "To change a result, fix the module that produces it and re-run the rule\n"
        "(e.g. snakemake --cores 1 <that output>). If you need a scratch copy to\n"
        "inspect, write it outside results/."
    )
