#!/usr/bin/env python3
"""Warn when a config key has no production caller (roadmap H11).

Advisory, never blocking: an unwired key is a claim that nothing implements
(invariant 3), and the right moment to hear about it is while the edit is still
in hand. Blocking would be wrong — a key can legitimately be added one commit
before its reader.

Runs two ways on purpose, because a hook whose event never fires is a gate that
lies. With a payload on stdin it behaves as a hook and only speaks when a
`config/*.yaml` file was touched. Called with `--all` it checks every config
file and exits non-zero on any finding, which is what `.claude/acceptance/`
uses — one implementation, two callers (the pattern `_prereg.py` endorses).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _config_keys import unwired_keys  # noqa: E402
from _hooklib import PROJECT_ROOT, read_payload, rel, target_path  # noqa: E402

CONFIG_FILES = (
    "config/config.yaml",
    "config/cell_lines.yaml",
    "config/ccle_depmap_ids.yaml",
)


def report(paths: list[Path]) -> list[str]:
    """Collect findings for the given config files.

    Args:
        paths: Config files to check.

    Returns:
        One human-readable line per unwired key.
    """
    import yaml

    lines: list[str] = []
    for path in paths:
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            lines.append(f"{rel(str(path))}: could not be parsed ({exc})")
            continue
        for dotted, reason in unwired_keys(parsed, Path(PROJECT_ROOT)):
            lines.append(f"{rel(str(path))}: `{dotted}` — {reason}")
    return lines


def main() -> int:
    """Run as a hook, or as a standalone check with ``--all``.

    Returns:
        Process exit status.
    """
    if "--all" in sys.argv:
        root = Path(PROJECT_ROOT)
        findings = report([root / name for name in CONFIG_FILES])
        for line in findings:
            print(f"  HATA {line}")
        if findings:
            print(
                f"\nGEÇMEDİ — {len(findings)} config anahtarının üretim çağıranı yok; "
                "bir anahtar eklemek onu bağlamaz (değişmez 3)"
            )
            return 1
        print("GEÇTİ — her config anahtarının üretimde bir çağıranı var")
        return 0

    payload = read_payload()
    path = target_path(payload)
    if not path:
        return 0
    touched = rel(path)
    if not any(touched == name for name in CONFIG_FILES):
        return 0

    findings = report([Path(path)])
    if not findings:
        return 0

    body = "\n".join(f"- {line}" for line in findings)
    json.dump(
        {
            "suppressOutput": True,
            "systemMessage": (
                f"{len(findings)} config key(s) have no production caller — "
                "see the context handed to the model"
            ),
            "hookSpecificOutput": {
                "hookEventName": payload.get("hook_event_name", "PostToolUse"),
                "additionalContext": (
                    "These config keys are not mentioned anywhere under `src/` or "
                    "`rules/`, so nothing can be reading them. Invariant 3: adding a "
                    f"key does not bind it.\n\n{body}\n\n"
                    "Either wire the key to a production caller or remove it. If it is "
                    "intentionally inert, say so in the roadmap rather than leaving the "
                    "declaration to be mistaken for behaviour."
                ),
            },
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
