"""The results directory must come from config, not from 89 hardcoded strings.

Audit 2026-11-19, Bulgu 11. ``--output-dir`` was accepted by ``cli.py``,
documented in ``README.md`` and passed to Snakemake as ``results_dir`` — which
no rule read, because every path was written out as ``"results/{gene}_..."``.
Supplying the flag therefore raised ``MissingRuleException``, and more
importantly there was **no supported way to run the pipeline without writing
over the reference runs** under ``results/``. The audit had to build a git
worktree to get an isolated run.

These tests lock the wiring rather than the fix, in the style of
``test_ci_workflow.py``: a future rule that hardcodes the prefix again would
silently reintroduce the flag's failure.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_RULES = sorted((_ROOT / "rules").glob("*.smk"))
_SNAKEFILE = _ROOT / "Snakefile"

#: A path literal that starts at the results directory instead of the prefix.
_HARDCODED = re.compile(r'"results/')


def test_there_are_rule_files_to_check() -> None:
    """Guard the guard: a glob that matches nothing would pass every test."""
    assert len(_RULES) >= 7, f"expected the seven stage rule files, found {len(_RULES)}"


def test_no_rule_file_hardcodes_the_results_prefix() -> None:
    offenders: list[str] = []
    for rule_file in _RULES:
        for lineno, line in enumerate(rule_file.read_text(encoding="utf-8").splitlines(), 1):
            if _HARDCODED.search(line):
                offenders.append(f"{rule_file.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "these rules build paths from a hardcoded 'results/' instead of "
        "RESULTS_DIR, so --output-dir would not reach them:\n  "
        + "\n  ".join(offenders)
    )


def test_snakefile_takes_the_prefix_from_config() -> None:
    text = _SNAKEFILE.read_text(encoding="utf-8")
    assert 'RESULTS_DIR = config.get("results_dir"' in text, (
        "Snakefile must read the prefix from config so that cli.py's "
        "--output-dir (passed as results_dir) actually reaches the rules"
    )
    assert not _HARDCODED.search(text), "Snakefile still hardcodes a results/ path"


def test_rules_concatenate_rather_than_f_string_the_prefix() -> None:
    """The wildcards must stay literal.

    ``f"{RESULTS_DIR}/{gene}_{cell_line}/..."`` would consume ``{gene}`` as an
    f-string field and need ``{{gene}}`` escaping in 89 places — one missed
    pair silently changes a rule's output pattern. Concatenation keeps the
    wildcards untouched, so this pins the safer form.
    """
    for rule_file in _RULES:
        text = rule_file.read_text(encoding="utf-8")
        assert 'f"{RESULTS_DIR}' not in text, (
            f"{rule_file.name} f-strings the prefix; use RESULTS_DIR + \"/...\" "
            "so the {gene}/{cell_line} wildcards need no escaping"
        )
        assert 'RESULTS_DIR + "/' in text, f"{rule_file.name} never uses RESULTS_DIR"
