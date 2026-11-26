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
class VerifiedCopy:
    """A place allowed to repeat a numeric fact *because* the value is checked.

    The rule in invariant 2's table is "do not copy, point at the authority".
    Its reason is that copies drift — and this repo has the scar: two docstrings
    still say "~250 genes" for a set of 183. A copy the gate recomputes from the
    authority on every run cannot drift silently, so it satisfies the reason
    while keeping a number a reader of the README actually wants. Deleting the
    number would satisfy the letter by destroying information; this does not.

    Attributes:
        path: Repository-relative file that may restate the value.
        pattern: Regex with one or more capture groups, each an integer that
            must equal the authority's current value.
        value_source: Name of the resolver that reads the authority.
    """

    path: str
    pattern: re.Pattern[str]
    value_source: str


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
    verified_copies: tuple[VerifiedCopy, ...] = ()


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


def _assigned_value(path: Path, name: str) -> Any:
    """Read a module-level assignment without importing the module.

    `ast` rather than an import on purpose: the gate runs in CI where `data/`
    is absent, and a module that touched a data file at import time would make
    the gate's own result depend on data availability.

    Args:
        path: Python file to parse.
        name: Module-level variable name.

    Returns:
        The literal value assigned to ``name``.

    Raises:
        ValueError: If the name is missing or is not a literal.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"{path} unparsable: {exc}") from exc
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = node.value
                if value is None:
                    continue
                try:
                    return ast.literal_eval(value)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{name} is not a literal") from exc
    raise ValueError(f"{path} defines no module-level {name!r}")


#: Which file answers for each numeric fact. One entry per resolver, and the
#: resolver returns the tuple of integers a verified copy must match.
_VALUE_SOURCES: dict[str, tuple[str, ...]] = {
    "background_gene_count": ("src/stage2_offtarget_scan/transcriptome_fetcher.py",),
    "promoter_window": ("config/config.yaml",),
    "seed_positions": ("src/stage2_offtarget_scan/seed_aligner.py", "config/config.yaml"),
    "seed_slice": ("src/stage2_offtarget_scan/seed_aligner.py", "config/config.yaml"),
    "dg_thresholds": ("config/config.yaml",),
}


def resolve_value(name: str, root: Path) -> tuple[int, ...]:
    """Compute a canonical numeric fact from its authority.

    Args:
        name: Resolver name, a key of ``_VALUE_SOURCES``.
        root: Repository root.

    Returns:
        The integers a verified copy of this fact must state, in order.

    Raises:
        ValueError: If the resolver is unknown or its source cannot be read.
    """
    import yaml

    def config() -> dict[str, Any]:
        text = (root / "config/config.yaml").read_text(encoding="utf-8")
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError("config/config.yaml is not a mapping")
        return loaded

    if name == "background_gene_count":
        genes = _assigned_value(
            root / "src/stage2_offtarget_scan/transcriptome_fetcher.py",
            "_BACKGROUND_GENES",
        )
        return (len(genes),)
    if name == "promoter_window":
        cfg = config()
        return (int(cfg["promoter_upstream"]), int(cfg["promoter_downstream"]))
    if name in {"seed_positions", "seed_slice"}:
        start = int(
            _assigned_value(
                root / "src/stage2_offtarget_scan/seed_aligner.py", "_SEED_START"
            )
        )
        length = int(config()["seed_length"])
        if name == "seed_positions":
            # 1-based inclusive, as rule 10 words it.
            return (start + 1, start + length)
        return (start, start + length)  # the Python slice bounds
    if name == "dg_thresholds":
        cfg = config()
        return (int(cfg["delta_g_strong"]), int(cfg["delta_g_moderate"]))
    raise ValueError(f"unknown value_source {name!r}")


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
        verified: list[VerifiedCopy] = []
        for item in entry.get("verified_copies", []) or []:
            if item.get("value_source") not in _VALUE_SOURCES:
                raise ValueError(
                    f"authority.yaml: {entry['id']!r} verified copy "
                    f"{item.get('path')!r} names unknown value_source "
                    f"{item.get('value_source')!r}"
                )
            compiled = re.compile(item["pattern"])
            if compiled.groups < 1:
                raise ValueError(
                    f"authority.yaml: verified copy {item['path']!r} has no "
                    "capture group — nothing to compare against the authority"
                )
            verified.append(
                VerifiedCopy(
                    path=item["path"],
                    pattern=compiled,
                    value_source=item["value_source"],
                )
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
                verified_copies=tuple(verified),
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
    # Verified copies are deliberately NOT exempt at file level: that would
    # excuse every other statement of the same fact in the file. Only the line
    # whose value the gate actually checks is excused — see `_line_is_verified`.
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


def stale_carve_outs(
    facts: list[Fact], status_by_id: dict[str, str], is_done: Any
) -> list[str]:
    """Carve-outs that have stopped meaning anything.

    Two ways, and both must be loud. A carve-out can name an item the roadmap
    never defines — nobody will ever close ``H99``. Or it can outlive its item:
    once that item is ``DONE`` the duplicate was supposed to go with it, so a
    carve-out still pointing there is an exemption whose removal date passed.

    Args:
        facts: Registered facts.
        status_by_id: Lower-cased roadmap item id to status cell.
        is_done: Predicate deciding whether a status counts as finished.

    Returns:
        Sorted, de-duplicated descriptions.
    """
    problems: list[str] = []
    for fact in facts:
        for carve in fact.carve_outs:
            key = carve.roadmap.lower()
            if key not in status_by_id:
                problems.append(
                    f"{carve.roadmap} ({carve.path}) — yol haritasında böyle bir "
                    "madde yok"
                )
            elif is_done(status_by_id[key]):
                problems.append(
                    f"{carve.roadmap} ({carve.path}) — madde KAPANDI, kopya onunla "
                    "birlikte gitmeliydi"
                )
    return sorted(set(problems))


def _line_is_verified(rel: str, line: str, fact: Fact) -> bool:
    """Whether this exact line is a declared, value-checked copy.

    Args:
        rel: Repository-relative path.
        line: The line's text.
        fact: The fact being checked.

    Returns:
        True when a verified-copy pattern for this path matches this line.
    """
    return any(
        verified.path == rel and verified.pattern.search(line)
        for verified in fact.verified_copies
    )


def check_verified_copies(root: Path, facts: list[Fact]) -> tuple[list[str], int]:
    """Confirm every declared verified copy still states the authority's value.

    Two failures are possible and both matter. A copy whose number no longer
    matches the authority is the drift the rule exists to stop. A copy whose
    pattern matches nothing any more is a **stale declaration**: the document
    stopped stating the fact, so the entry is now an exemption guarding
    nothing, and the next real duplicate in that file would pass unseen.

    Args:
        root: Repository root.
        facts: Registered facts.

    Returns:
        A ``(problems, checked)`` pair.
    """
    problems: list[str] = []
    checked = 0
    for fact in facts:
        for verified in fact.verified_copies:
            path = root / verified.path
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"{verified.path}: okunamadı ({exc})")
                continue
            try:
                expected = resolve_value(verified.value_source, root)
            except (ValueError, KeyError, OSError) as exc:
                problems.append(
                    f"{verified.path}: otorite değeri çözümlenemedi "
                    f"({verified.value_source}): {exc}"
                )
                continue
            matches = list(verified.pattern.finditer(text))
            if not matches:
                problems.append(
                    f"{verified.path}: doğrulanmış kopya beyanı BAYAT — deseni "
                    f"({verified.pattern.pattern}) artık hiçbir satırla eşleşmiyor, "
                    "yani muafiyet hiçbir şeyi korumuyor"
                )
                continue
            for match in matches:
                checked += 1
                stated = tuple(int(g) for g in match.groups() if g is not None)
                if stated != expected:
                    line = text[: match.start()].count("\n") + 1
                    problems.append(
                        f"{verified.path}:{line}: {stated} yazıyor, otorite "
                        f"({verified.value_source}) {expected} diyor"
                    )
    return problems, checked


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
                if line_states_fact(
                    line, fact, context="\n".join(near)
                ) and not _line_is_verified(rel, line, fact):
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
        value_problems: Verified copies that disagree with the authority or
            whose declaration has gone stale.
        values_checked: How many restated numbers were compared.
    """

    violations: list[Violation] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    unmeasured: dict[str, str] = field(default_factory=dict)
    carve_out_count: int = 0
    table_mismatch: list[str] = field(default_factory=list)
    dangling_carve_outs: list[str] = field(default_factory=list)
    value_problems: list[str] = field(default_factory=list)
    values_checked: int = 0

    @property
    def ok(self) -> bool:
        """Whether the gate passes.

        Returns:
            True when nothing states a foreign fact, the table agrees with the
            registry, every carve-out names a real roadmap item, and every
            verified copy still matches the authority.
        """
        return (
            not self.violations
            and not self.table_mismatch
            and not self.dangling_carve_outs
            and not self.value_problems
        )
