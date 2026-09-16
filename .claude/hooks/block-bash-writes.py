#!/usr/bin/env python3
"""PreToolUse guard: refuse Bash commands that write into data/ or results/.

The Write/Edit/MultiEdit guards left the whole shell open —
``echo '{}' > results/VEGFA_HeLa/stage5_deltag.json`` reached the file with
nothing in its way, so the data-fabrication path the results/ guard exists to
close was still wide open.

What is checked: shell redirections (``>``, ``>>``, ``&>``, ``>|``) and the
commands that write or destroy in place — tee, sed -i, cp, mv, rm, truncate,
dd, chmod. Reads are deliberately untouched: cat, head, sed without -i, grep,
jq, wc, ls, python3 -c reading a JSON all pass, because auditing a run means
reading these files constantly and a guard that blocks inspection would just
be turned off.

Snakemake is exempt. It is the only legitimate writer of results/, so any
command invoking it (``snakemake ...``, ``python -m snakemake ...``) passes
whole. That exemption is a substring match on the command, which something
like ``rm -rf data/  # snakemake`` would slip past. This is a guardrail
against absent-minded damage, not a security boundary; treat it as such.

Not caught: a write performed inside an interpreter, e.g.
``python3 -c "open('results/x.json','w')..."``. Catching that would mean
parsing Python from a hook.
"""

from __future__ import annotations

import os
import re
import shlex
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT, block, read_payload, rel, under  # noqa: E402

GUARDED = ("data", "results")

# Shell control operators: each starts a new command in the same line.
SEPARATORS = {";", "|", "||", "&&", "&", "(", ")", "\n", "|&"}
REDIRECTS = {">", ">>", "&>", ">|", ">&"}

SNAKEMAKE = re.compile(r"(?<![\w-])snakemake(?![\w-])")

# Commands whose *every* path argument is at risk: they delete or rewrite.
DESTRUCTIVE = {"rm", "mv", "truncate", "chmod", "shred", "unlink", "rmdir"}
# Commands where only the destination is written; sources are just read.
DEST_ONLY = {"cp", "install", "rsync", "ln"}


def segments(tokens: list[str]) -> list[list[str]]:
    """Split a token stream into individual commands on shell operators."""
    out: list[list[str]] = [[]]
    for token in tokens:
        if token in SEPARATORS:
            out.append([])
        else:
            out[-1].append(token)
    return [seg for seg in out if seg]


def resolve(arg: str) -> str | None:
    """Absolute, ``..``-resolved path for a token that looks like a path."""
    if not arg or arg.startswith("-"):
        return None
    if not os.path.isabs(arg):
        arg = os.path.join(PROJECT_ROOT, arg)
    return os.path.realpath(arg)


def guarded(arg: str) -> str | None:
    """Return the resolved path if it lands in data/ or results/, else None."""
    path = resolve(arg)
    return path if path and under(path, *GUARDED) else None


def paths(args: list[str]) -> list[str]:
    """Non-flag arguments, with the value of a flag like ``-t DIR`` dropped."""
    out: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("-t", "--target-directory", "-S", "--suffix"):
            skip = True
            continue
        if arg.startswith("-"):
            continue
        out.append(arg)
    return out


def write_targets(seg: list[str]) -> list[str]:
    """Every path this one command would create, overwrite, or destroy."""
    targets: list[str] = []

    # Redirections, whichever command they are attached to.
    for i, token in enumerate(seg):
        if token in REDIRECTS and i + 1 < len(seg):
            targets.append(seg[i + 1])
        elif token.startswith(">") and len(token.lstrip(">&|")) > 0:
            targets.append(token.lstrip(">&|"))

    argv = [t for t in seg if t not in REDIRECTS]
    if not argv:
        return targets
    name = os.path.basename(argv[0])
    args = argv[1:]

    if name == "tee":
        targets += paths(args)
    elif name == "sed":
        # Only -i / --in-place rewrites the file; plain sed just reads. -i is
        # the sole short flag carrying an "i", so -ri and -i.bak count too.
        in_place = any(
            a.startswith("--in-place") or (a.startswith("-") and not a.startswith("--") and "i" in a)
            for a in args
        )
        if in_place:
            targets += paths(args)[1:]  # first non-flag arg is the sed script
    elif name == "dd":
        targets += [a.split("=", 1)[1] for a in args if a.startswith("of=")]
    elif name in DESTRUCTIVE:
        targets += paths(args)
    elif name in DEST_ONLY:
        explicit = [args[i + 1] for i, a in enumerate(args) if a in ("-t", "--target-directory") and i + 1 < len(args)]
        if explicit:
            targets += explicit
        else:
            rest = paths(args)
            if len(rest) >= 2:
                targets.append(rest[-1])

    return targets


payload = read_payload()
tool_input = payload.get("tool_input")
command = tool_input.get("command") if isinstance(tool_input, dict) else None

if not isinstance(command, str) or not command.strip():
    sys.exit(0)

# Snakemake owns results/. Let its runs through untouched.
if SNAKEMAKE.search(command):
    sys.exit(0)

try:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
except ValueError:
    # Unbalanced quotes and the like: not our business to adjudicate.
    sys.exit(0)

hits: list[str] = []
for seg in segments(tokens):
    for target in write_targets(seg):
        path = guarded(target)
        if path and rel(path) not in hits:
            hits.append(rel(path))

if hits:
    where = "\n".join(f"  - {h}" for h in hits)
    block(
        f"BLOCKED: this command writes to protected paths:\n{where}\n\n"
        "data/ is read-only reference data (~1.5 GB, partly licence-gated and not\n"
        "re-downloadable). results/ holds pipeline measurements — writing there by\n"
        "hand fabricates data that afterwards reads as a genuine run.\n\n"
        "Snakemake is the only thing allowed to write results/; any command that\n"
        "invokes it passes. To change a result, fix the module and re-run the rule:\n"
        "  snakemake --cores 1 results/<gene>_<cell_line>/<output>.json\n"
        "Reading is unrestricted — cat, head, grep, jq, sed without -i all work."
    )
