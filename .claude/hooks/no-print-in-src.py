#!/usr/bin/env python3
"""PreToolUse guard: refuse print() written into src/*.py.

The project logs through loguru; a print() in a pipeline module writes to
stdout, which Snakemake captures separately from the log and which nothing
downstream reads. src/cli.py is exempt — that is the user-facing CLI, where
printing is the point.
"""

from __future__ import annotations

import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import block, read_payload, rel, target_path, under, written_text  # noqa: E402

# Bare builtin print only: `pprint(`, `console.print(` and `self.print(` are
# somebody else's function, not the builtin this rule is about.
PRINT_CALL = re.compile(r"(?<![\w.])print\s*\(")

payload = read_payload()
path = target_path(payload)

if path and path.endswith(".py") and under(path, "src") and not path.endswith("/src/cli.py"):
    if PRINT_CALL.search(written_text(payload)):
        block(
            f"BLOCKED: this writes a print() call into {rel(path)}.\n"
            "orcSONAR logs with loguru, never print() — stdout from a pipeline module\n"
            "is not captured as log output. Use:\n"
            "    from loguru import logger\n"
            "    logger.info(...) / logger.warning(...) / logger.debug(...)\n"
            "src/cli.py is the only exemption, since its output goes to the user."
        )
