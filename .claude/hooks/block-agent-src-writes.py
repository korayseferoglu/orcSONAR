#!/usr/bin/env python3
"""PreToolUse guard: a subagent may not write `src/` unless it is an implementer.

Roadmap H13, inherited from H3. Several agent briefs declare themselves
read-only — `bio-reviewer` says "You are read-only: report findings, never
edit" — while their `tools:` list hands them `Write`. A brief is not an
enforcement mechanism, and this project has a whole invariant about that
(invariant 3: declared is not implemented).

Why a hook and not frontmatter: subagent frontmatter has **no** `permissions`
field, and an unrecognised field there is silently ignored — so writing
`permissions:` into an agent file would create a protection that does not
exist. A settings-level `Edit(src/**)` deny would work but is session-wide and
would block the main session too. `PreToolUse` hooks do fire for subagent tool
calls, and the payload carries `agent_id` and `agent_type`, which makes this
the only enforcement point that can tell a subagent apart from the main thread.

`agent_id` is the signal used, because `agent_type` is also set when the main
session itself is started with `--agent`.
"""

from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import block, read_payload, rel, target_path, under  # noqa: E402

#: Agents whose job is to change production code. `coordinate-engineer` owns
#: the Phase D coordinate migration — the highest-risk change in the project —
#: and cannot do it without writing `src/`. Anything not listed here is either
#: a reviewer or a fetcher, and a reviewer that can edit the code it reviews is
#: not a reviewer.
IMPLEMENTERS: frozenset[str] = frozenset({"coordinate-engineer"})

payload = read_payload()
path = target_path(payload)
agent_id = payload.get("agent_id")
agent_type = str(payload.get("agent_type") or "")

if path and agent_id and under(path, "src") and agent_type not in IMPLEMENTERS:
    block(
        f"BLOCKED: subagent {agent_type or '(unnamed)'} tried to write "
        f"{rel(path)}.\n\n"
        "Agents other than the declared implementers are reviewers, auditors or\n"
        "fetchers. Their findings come back as the agent's report — which the\n"
        "harness persists on its own when it is long — so none of them needs to\n"
        "edit production code, and several of their own briefs say they must not.\n\n"
        f"Implementers allowed to write src/: {', '.join(sorted(IMPLEMENTERS))}.\n"
        "Write the finding into the report, or into reports/ if a file is needed."
    )
