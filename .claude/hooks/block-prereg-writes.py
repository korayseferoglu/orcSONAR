#!/usr/bin/env python3
"""PreToolUse guard: refuse any write to a committed pre-registration.

Invariant 6. Until this hook existed, `docs/PRE_REGISTRATION.md` was protected
by a sentence in a document and by the `pre-register` skill — and that skill
only guards the path where the file is *created*. An `Edit` on a committed
pre-registration walked straight through, because a skill is invoked
deliberately and a hook is not. The status block said so plainly on every
launch: "yaptırım: H8 kurulmadı".

The violation this stops is not a typo. It is seeing a result and then moving
the metric or the threshold it is measured against — a small commit, three
months later, in a file nobody rereads. `docs/PRE_REGISTRATION_v2.md` is the
legal route and is never blocked: a lock with no way around it gets defeated
instead of followed.

Decision logic and the git check live in `_prereg.py`, shared with the
`pre-register` skill so the two cannot disagree about what "locked" means.
"""

from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import _prereg  # noqa: E402, I001
from _hooklib import PROJECT_ROOT, block, read_payload, rel, target_path  # noqa: E402

payload = read_payload()
path = target_path(payload)

if path:
    root = _prereg.project_root(PROJECT_ROOT)
    if _prereg.is_locked_target(path, root):
        committed = _prereg.git_committed(path, root)
        if _prereg.refuses(locked=True, committed=committed):
            why = (
                "it is committed — invariant 6 makes it read-only forever"
                if committed
                else (
                    "its git state could not be read, and a lock that cannot tell\n"
                    "must refuse: ÖLÇÜLMEDİ is not permission"
                )
            )
            block(
                f"BLOCKED: {rel(path)} may not be edited — {why}.\n\n"
                f"The only legal change is a new {_prereg.SUCCESSOR_RELATIVE}, with\n"
                "BOTH versions reported in the publication. Open it, write what is\n"
                "changing and why, and leave the original untouched.\n\n"
                "If you are about to move a metric, a threshold or an exclusion rule\n"
                "after seeing a result: that is the violation this rule exists for,\n"
                "and it is the one nobody would notice three months from now.\n"
                "A negative result is an accepted outcome with a publication path\n"
                "(invariant 7) — searching for a positive one by tuning the plan is\n"
                "not."
            )
