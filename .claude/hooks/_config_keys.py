"""Which config keys production actually reads — pure logic for roadmap H11.

Invariant 3: a declaration is not an implementation. Adding a key to
``config.yaml`` binds nothing, and this repo has the measurements to prove the
point — ``mypy strict=true`` with the tool not installed, ``max_mismatches: 12``
eliminating no candidate, ``h3k27me3`` with nine config definitions and zero
production references.

So this module answers one question for each key: **does anything under
``src/`` or ``rules/`` mention it?** A mention is a weak test — the key could
be named in a comment — but the inverse is strong: a key that appears nowhere
in production cannot possibly be read, and that is the direction worth
blocking on.

Known residual weakness, stated rather than hidden: a quoted key name
anywhere in production excuses the key, even when the quote is unrelated. The
`api_rate_limits.ensembl` entry is excused by `cache.py`'s
`{"ensembl": 1, ...}` schema-version map, which has nothing to do with rate
limiting. Closing that needs real config-flow analysis; until then the check is
sound in one direction only — a flagged key is definitely unread, an unflagged
key is merely *mentioned*.

``rules/`` counts as production because the Snakemake rules *are* the pipeline;
most config values reach a module as a rule parameter rather than through a
direct lookup, so searching ``src/`` alone would flag most of the file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

#: Directories that count as production code.
PRODUCTION_DIRS: tuple[str, ...] = ("src", "rules", "Snakefile")

#: Keys whose own name is never expected in code, with the reason. A parent
#: mapping is read through its children, so the parent name may legitimately be
#: absent — but only when at least one child IS referenced, which
#: `unwired_keys` checks rather than assumes.
PARENT_OK = "parent mapping: read through its children"

#: Objects a config key is actually read off. Anchoring the attribute form to
#: these is not cosmetic: a bare `\.key\b` also matches a dotted hostname, so
#: `"https://rest.ensembl.org"` counted as a read of the `ensembl` key and
#: excused the whole `api_rate_limits` block. Measured against the repository:
#: `config.` (5), `args.` (4), `params.` (1).
RECEIVERS: tuple[str, ...] = ("config", "cfg", "conf", "params", "settings", "args", "self")


def flatten_keys(mapping: Any, prefix: str = "") -> list[tuple[str, str, bool]]:
    """List every key in a parsed YAML mapping.

    Args:
        mapping: Parsed YAML.
        prefix: Dotted prefix for nested keys.

    Returns:
        ``(dotted_name, leaf_name, is_parent)`` for each key, depth first.
    """
    out: list[tuple[str, str, bool]] = []
    if not isinstance(mapping, dict):
        return out
    for key, value in mapping.items():
        name = str(key)
        is_parent = isinstance(value, dict) and bool(value)
        out.append((f"{prefix}{name}", name, is_parent))
        if is_parent:
            out.extend(flatten_keys(value, f"{prefix}{name}."))
    return out


def lookup_pattern(leaf: str) -> str:
    """Regex matching ``leaf`` used as a key, not merely as a word.

    A bare-word search is too weak to mean anything: key names like ``ensembl``
    and ``gnomad`` also occur in URLs, module names and prose, so searching for
    the word excused the whole ``api_rate_limits`` block while nothing read it.
    A key is only *readable* if it appears as a quoted string (``config["x"]``,
    ``.get("x")``) or as an attribute (``params.x``, ``config.x``), so that is
    what gets searched.

    Args:
        leaf: The bare key name.

    Returns:
        An extended-regex string for ``git grep -E``.
    """
    escaped = re.escape(leaf)
    receivers = "|".join(RECEIVERS)
    return f"[\"']{escaped}[\"']|\\b({receivers})\\.{escaped}\\b"


def mentions(leaf: str, repo_root: Path) -> list[str]:
    """Files under the production directories that read ``leaf`` as a key.

    Args:
        leaf: The bare key name.
        repo_root: Repository root.

    Returns:
        Repository-relative paths, empty when nothing reads it.
    """
    # Only pass paths that exist. `git grep` treats a missing pathspec as a
    # fatal error and returns non-zero, which this function would otherwise
    # read as "nothing mentions it" — making every key look unwired the moment
    # one production directory is renamed.
    present = [name for name in PRODUCTION_DIRS if (repo_root / name).exists()]
    if not present:
        return []
    try:
        done = subprocess.run(
            ["git", "grep", "-lE", "--", lookup_pattern(leaf), *present],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if done.returncode != 0:
        return []
    return [line for line in done.stdout.splitlines() if line.strip()]


def unwired_keys(mapping: Any, repo_root: Path) -> list[tuple[str, str]]:
    """Keys that no production file mentions.

    A parent mapping is excused only when at least one of its children is
    mentioned — otherwise the whole block is unread and saying "it is read
    through its children" would be the excuse doing the lying.

    Args:
        mapping: Parsed YAML of one config file.
        repo_root: Repository root.

    Returns:
        ``(dotted_name, reason)`` pairs for every unwired key.
    """
    keys = flatten_keys(mapping)
    seen: dict[str, bool] = {
        dotted: bool(mentions(leaf, repo_root)) for dotted, leaf, _ in keys
    }

    unwired: list[tuple[str, str]] = []
    for dotted, _leaf, is_parent in keys:
        if seen[dotted]:
            continue
        if is_parent:
            children = [
                other
                for other in seen
                if other.startswith(f"{dotted}.") and seen[other]
            ]
            if children:
                continue
            unwired.append(
                (dotted, "whole block unread: neither it nor any child is mentioned")
            )
            continue
        unwired.append((dotted, "no production file reads it (searched src/, rules/, Snakefile)"))
    return unwired
