#!/usr/bin/env python3
"""InstructionsLoaded: record which instruction files actually loaded.

`.claude/rules/*.md` load at launch (no frontmatter) or on demand when Claude
touches a file matching their `paths:` globs. Neither is observable from inside
the session that configured them, so without this a wrong glob or an unsupported
key is indistinguishable from a working one — the rule file sits there inert and
everyone assumes it is in effect. That is this project's signature failure
(invariant 3: declared is not wired), and writing the rules without an
instrument to check them would have reproduced it at the level of the fix.

Appends one JSON line per load to .claude/instructions-loaded.log (gitignored).
Read it with:

    python3 -c "import json;[print(json.loads(l)['file_path']) for l in open('.claude/instructions-loaded.log')]"

or let the SessionStart hook (roadmap H4) summarise it. Advisory only: this
event cannot block, and any failure here exits 0 rather than disturbing a load.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT, read_payload  # noqa: E402

LOG = f"{PROJECT_ROOT}/.claude/instructions-loaded.log"
KEEP = ("file_path", "memory_type", "load_reason", "globs", "trigger_file_path")

payload = read_payload()
if not payload:
    sys.exit(0)

entry = {"at": datetime.now(UTC).isoformat(timespec="seconds")}
entry.update({k: payload[k] for k in KEEP if k in payload})

try:
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
except OSError:
    pass  # a logger that breaks a session is worse than no logger

sys.exit(0)
