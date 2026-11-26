"""Single-copy gate — pure logic for roadmap H9.

A canonical fact belongs in exactly one file. The second copy starts to drift,
and the copy that drifts is the one that stops protecting anything: a wrong
``0.5`` had spread to five files in this repo and one of them had quietly
disabled a QA gate.

This module answers one question: **does any file state a canonical fact that
it is not the authority for?** It is deliberately split from its callers —
``.claude/acceptance/H9.sh`` and the CI step both run the same implementation,
which is the pattern ``_prereg.py`` endorses while citing H9.

Three distinctions carry the whole design, and each exists because a naive
grep got them wrong somewhere in this repo already:

1. **Stating a fact vs. pointing at it.** ``10-koordinatlar.md`` contains the
   string "chr-prefix" inside the sentence "the chr-prefix table is NOT here".
   A line that names a fact in order to send the reader elsewhere is the
   behaviour the rule wants, not a violation.
2. **Prose vs. code.** ``seq[1:8]`` is the seed slice being *used*; a comment
   saying "seed is positions 2-8" is the fact being *restated*. Only prose is
   scanned — in Python that means docstrings and comments, never expressions.
   Duplicated *constants* in code are a real but different finding, and this
   gate says so rather than pretending to cover them.
3. **Open debt vs. new drift.** Today's tree is not clean on a literal reading
   of the authority table. Carve-outs make that debt explicit and each one
   names the roadmap item that removes it, so the gate still goes red for
   anything *new*. A gate that passed by scanning nothing would be worse than
   no gate (``.claude/acceptance/README.md``, "exit 0 yazma tuzağı").
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Files and trees that never count as a second copy, with the reason each is
#: exempt. These are *policy* exemptions, not deferred work: nothing in the
#: roadmap will remove them.
POLICY_EXEMPT: dict[str, str] = {
    "AUDIT.md": (
        "dated evidence document — invariant 2 cites it; rewriting the record "
        "to satisfy a gate would falsify the evidence"
    ),
    "reports/": "generated output, not authored prose",
    "results/": "pipeline output (invariant 1)",
    "data/": "read-only reference data (invariant 1)",
    ".claude/acceptance/": (
        "acceptance scripts must name the value they measure, or they cannot "
        "measure it"
    ),
    ".claude/hooks/_single_copy.py": "this file: the gate names the facts it scans",
    "tests/hooks/test_single_copy.py": (
        "the gate's own tests must quote the sentences they detect, for the "
        "same reason the acceptance scripts must name the value they measure"
    ),
    ".claude/agents/": (
        "a subagent does not inherit CLAUDE.md or `.claude/rules/*` — the glob "
        "that loads a rule file never fires for it, so an agent brief that "
        "pointed at rule 10 instead of restating it would point at something "
        "the agent cannot read. Both briefs state this rationale themselves. "
        "Policy exemption, not deferred work"
    ),
    ".claude/authority.yaml": "the registry itself",
    "SCIENTIFIC_ROADMAP.md": (
        "the roadmap records every finding's evidence, including the wrong "
        "values a finding is about; it is also an authority in its own right"
    ),
}


@dataclass(frozen=True)
class CarveOut:
    """One known-open duplicate, with the roadmap item that will remove it.

    Attributes:
        path: Repository-relative path prefix the carve-out covers.
        roadmap: Roadmap item id that closes it, e.g. ``B8``.
        reason: Why it is still there.
    """

    path: str
    roadmap: str
    reason: str


@dataclass(frozen=True)
class Fact:
    """A canonical fact, its authority, and how to spot it being restated.

    Attributes:
        id: Registry key, matching the id column of the authority table.
        gercek: The fact as the authority table words it.
        otorite: Repository-relative path of the single authority.
        patterns: Regexes whose match means the fact is being stated. Empty
            means the fact is registered but **not machine-measurable**; the
            gate reports that rather than implying coverage.
        unmeasured_reason: Why ``patterns`` is empty.
        co_patterns: When non-empty, a line must match one of these *as well*
            as a ``patterns`` entry. This is what separates "which source needs
            a chr prefix" (the fact) from "this parameter expects chr-prefixed
            input" (a function's own interface contract).
        declared_summaries: Paths allowed to repeat the fact because they are
            declared summaries of the authority.
        definition_sites: Paths where the value legitimately lives in code, so
            a docstring documenting it there is definition, not duplication.
        pointer_tokens: Substrings that mark a line as pointing at the
            authority instead of stating the fact.
        scope: Path prefixes to scan. Empty means the whole repository.
        carve_outs: Known-open duplicates.
    """

    id: str
    gercek: str
    otorite: str
    patterns: tuple[re.Pattern[str], ...] = ()
    co_patterns: tuple[re.Pattern[str], ...] = ()
    unmeasured_reason: str = ""
    declared_summaries: tuple[str, ...] = ()
    definition_sites: tuple[str, ...] = ()
    pointer_tokens: tuple[str, ...] = ()
    scope: tuple[str, ...] = ()
    carve_outs: tuple[CarveOut, ...] = ()


@dataclass(frozen=True)
class Violation:
    """A line that states a fact it is not the authority for.

    Attributes:
        fact_id: Which fact.
        path: Repository-relative file path.
        line: 1-based line number.
        text: The offending line, stripped.
    """

    fact_id: str
    path: str
    line: int
    text: str


#: Markers that turn a hit into a pointer or a disclaimer rather than a claim.
#: "DEĞİL" is load-bearing: `10-koordinatlar.md` states the fact's *name* in
#: the very sentence that refuses to restate its content.
DISCLAIMER_TOKENS: tuple[str, ...] = (
    "değil",
    "DEĞİL",
    "burada yok",
    "not here",
    "otorite",
    "authority",
    "bkz",
    "see ",
    "kopyalama",
)

#: Markers that make a line a record of what a fact USED to be. This project
#: keeps its evidence trail deliberately — invariant 2's own text narrates the
#: wrong `0.5` it replaced — and a dated past-tense sentence creates no drift
#: risk about the current value. It is the present-tense restatement that does.
HISTORY_TOKENS: tuple[str, ...] = (
    "eskiden",
    "no longer",
    "used to",
    "replaced",
    "kapandı",
    "before b2",
    "until 2026",
    "pre-c3",
    "artık",
)

_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".toml", ".cfg", ".txt", ".sh"}


def load_registry(raw: dict[str, Any]) -> list[Fact]:
    """Build the fact list from the parsed ``authority.yaml``.

    Args:
        raw: Parsed YAML mapping with a ``facts`` list.

    Returns:
        The registered facts.

    Raises:
        ValueError: If a required key is missing, because a half-registered
            fact would be scanned as if it had no authority.
    """
    facts: list[Fact] = []
    for entry in raw.get("facts", []):
        for key in ("id", "gercek", "otorite"):
            if not entry.get(key):
                raise ValueError(f"authority.yaml: fact missing {key!r}: {entry!r}")
        patterns = tuple(
            re.compile(p, re.IGNORECASE) for p in entry.get("patterns", []) or []
        )
        co_patterns = tuple(
            re.compile(p, re.IGNORECASE) for p in entry.get("co_patterns", []) or []
        )
        reason = entry.get("unmeasured_reason", "") or ""
        if not patterns and not reason:
            raise ValueError(
                f"authority.yaml: {entry['id']!r} has no patterns and no "
                "unmeasured_reason — silent non-coverage is the exit-0 trap"
            )
        carve_outs = tuple(
            CarveOut(path=c["path"], roadmap=c["roadmap"], reason=c.get("reason", ""))
            for c in entry.get("carve_outs", []) or []
        )
        for carve in carve_outs:
            if not carve.roadmap:
                raise ValueError(
                    f"authority.yaml: carve-out {carve.path!r} names no roadmap "
                    "item — an exemption nobody will ever remove is a deletion"
                )
        facts.append(
            Fact(
                id=entry["id"],
                gercek=entry["gercek"],
                otorite=entry["otorite"],
                patterns=patterns,
                co_patterns=co_patterns,
                unmeasured_reason=reason,
                declared_summaries=tuple(entry.get("declared_summaries", []) or []),
                definition_sites=tuple(entry.get("definition_sites", []) or []),
                pointer_tokens=tuple(entry.get("pointer_tokens", []) or []),
                scope=tuple(entry.get("scope", []) or []),
                carve_outs=carve_outs,
            )
        )
    return facts


def prose_lines(path: Path, text: str) -> list[tuple[int, str]]:
    """Return the lines of ``text`` that are prose rather than code.

    For Python, prose means docstrings and comments: a numeric literal in an
    expression is the fact being used or defined, not restated. For text
    formats every line is prose.

    Args:
        path: The file's path, used only for its suffix.
        text: File contents.

    Returns:
        ``(1-based line number, line text)`` pairs.
    """
    if path.suffix != ".py":
        if path.suffix in _TEXT_SUFFIXES or not path.suffix:
            return list(enumerate(text.splitlines(), start=1))
        return []

    keep: dict[int, str] = {}
    lines = text.splitlines()

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                keep[tok.start[0]] = lines[tok.start[0] - 1]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return sorted(keep.items())

    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None or not node.body:
            continue
        first = node.body[0]
        start = getattr(first, "lineno", None)
        end = getattr(first, "end_lineno", None)
        if start is None or end is None:
            continue
        for n in range(start, end + 1):
            if 1 <= n <= len(lines):
                keep[n] = lines[n - 1]

    return sorted(keep.items())


def _is_exempt_path(rel: str, fact: Fact) -> str:
    """Return the reason ``rel`` is exempt for ``fact``, or an empty string.

    Args:
        rel: Repository-relative path.
        fact: The fact being checked.

    Returns:
        A human-readable reason, or ``""`` when the path must be scanned.
    """
    if rel == fact.otorite:
        return "authority"
    for prefix, reason in POLICY_EXEMPT.items():
        if rel == prefix or rel.startswith(prefix):
            return reason
    for summary in fact.declared_summaries:
        if rel == summary or rel.startswith(summary):
            return "declared summary"
    for site in fact.definition_sites:
        if rel == site or rel.startswith(site):
            return "definition site"
    for carve in fact.carve_outs:
        if rel == carve.path or rel.startswith(carve.path):
            return f"carve-out → {carve.roadmap}"
    return ""


#: How many neighbouring prose lines a disclaimer can reach. `10-koordinatlar.md`
#: names two formats' coordinate bases on one line and refuses to own them on
#: the next ("Buraya kopyalamıyorum; iki kopya kaymaya başlar"). Judging that
#: line alone reads it as the very duplication it is declining to make.
DISCLAIMER_RADIUS = 2


def line_states_fact(line: str, fact: Fact, context: str = "") -> bool:
    """Whether ``line`` states ``fact`` rather than pointing at it.

    Args:
        line: One line of prose.
        fact: The fact being checked.
        context: The neighbouring prose lines, searched for disclaimers only.

    Returns:
        True when the line matches a pattern and carries no pointer or
        disclaimer marker.
    """
    if not any(p.search(line) for p in fact.patterns):
        return False
    if fact.co_patterns and not any(p.search(line) for p in fact.co_patterns):
        return False
    lowered = line.lower()
    for token in fact.pointer_tokens:
        if token.lower() in lowered:
            return False
    for token in (*DISCLAIMER_TOKENS, *HISTORY_TOKENS):
        if token.lower() in lowered:
            return False
    neighbourhood = context.lower()
    for token in (*DISCLAIMER_TOKENS, *HISTORY_TOKENS):
        if token.lower() in neighbourhood:
            return False
    return True


def scan(
    root: Path, facts: list[Fact], files: list[str]
) -> tuple[list[Violation], dict[str, int]]:
    """Scan ``files`` for facts stated outside their authority.

    Args:
        root: Repository root.
        facts: Registered facts.
        files: Repository-relative paths to scan.

    Returns:
        A ``(violations, skipped_counts)`` pair, where ``skipped_counts`` maps
        an exemption reason to how many files it covered.
    """
    violations: list[Violation] = []
    skipped: dict[str, int] = {}

    cache: dict[str, list[tuple[int, str]]] = {}

    for fact in facts:
        if not fact.patterns:
            continue
        for rel in files:
            if fact.scope and not any(rel.startswith(s) for s in fact.scope):
                continue
            reason = _is_exempt_path(rel, fact)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            if rel not in cache:
                path = root / rel
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    cache[rel] = []
                else:
                    cache[rel] = prose_lines(path, text)
            entries = cache[rel]

            for index, (number, line) in enumerate(entries):
                near = [
                    entries[j][1]
                    for j in range(
                        max(0, index - DISCLAIMER_RADIUS),
                        min(len(entries), index + DISCLAIMER_RADIUS + 1),
                    )
                    if j != index
                    and abs(entries[j][0] - number) <= DISCLAIMER_RADIUS
                ]
                if line_states_fact(line, fact, context="\n".join(near)):
                    violations.append(
                        Violation(
                            fact_id=fact.id,
                            path=rel,
                            line=number,
                            text=line.strip()[:160],
                        )
                    )
    return violations, skipped


_TABLE_ROW = re.compile(r"^\|\s*`?(?P<id>[a-z_]+)`?\s*\|(?P<rest>.*)\|\s*$")


def authority_table_ids(markdown: str) -> list[str]:
    """Extract the id column of the authority table in ``00-degismezler.md``.

    The prose table and ``authority.yaml`` are two renderings of one fact, so
    the gate checks them against each other — the single-copy rule applied to
    the registry itself.

    Args:
        markdown: Contents of ``.claude/rules/00-degismezler.md``.

    Returns:
        The ids listed in the table, in order.
    """
    ids: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if line.startswith("## Kanonik gerçekler nerede yazılı"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if not inside:
            continue
        match = _TABLE_ROW.match(line.strip())
        if match and match.group("id") not in {"id", "gercek"}:
            ids.append(match.group("id"))
    return ids


@dataclass
class Report:
    """The gate's full result.

    Attributes:
        violations: Lines stating a fact outside its authority.
        skipped: Exemption reason to file count.
        unmeasured: Fact id to the reason it carries no patterns.
        carve_out_count: How many carve-outs the registry holds.
        table_mismatch: Ids that differ between the table and the registry.
        dangling_carve_outs: Carve-outs naming a roadmap item that does not
            exist, which would make them permanent by accident.
    """

    violations: list[Violation] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    unmeasured: dict[str, str] = field(default_factory=dict)
    carve_out_count: int = 0
    table_mismatch: list[str] = field(default_factory=list)
    dangling_carve_outs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the gate passes.

        Returns:
            True when nothing states a foreign fact, the table agrees with the
            registry, and every carve-out names a real roadmap item.
        """
        return (
            not self.violations
            and not self.table_mismatch
            and not self.dangling_carve_outs
        )
