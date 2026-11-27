"""Run provenance — what code, config and data produced a directory of results.

Roadmap H10. Without this, a directory under ``results/`` is an orphan: it
carries numbers and no account of where they came from. That is not an abstract
risk here — the four existing runs turned out to be in an obsolete two-part
``site_id`` format, and the only way anyone found out was by reading them.

The hard part is honesty about what a manifest can and cannot claim. A manifest
written *after* a run cannot prove which commit produced it, and this module
refuses to pretend otherwise. It records what is checkable:

* the commit at the time of writing, and whether the worktree was clean,
* a **verdict** on whether that commit could even be the producer, derived from
  commit time against output mtimes — so a manifest generated today for a run
  from September says plainly that HEAD cannot have produced it,
* content hashes of every output, which make later tampering detectable
  regardless of provenance,
* fingerprints of the config files and the external-data manifest,
* installed versions of the pinned dependencies, so an environment that drifted
  from ``pyproject.toml`` is visible.

What it deliberately does **not** contain is a ``seeds`` field. The roadmap row
asked for one, but ``git grep`` over ``src/`` finds no ``random``, ``np.random``,
``secrets``, ``shuffle`` or ``sample(`` — the pipeline has no stochastic
component, so an empty ``seeds: {}`` would advertise bookkeeping that tracks
nothing. The absence is recorded as a claim with its evidence instead.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from src.core import ensembl_release

SCHEMA_VERSION = 1

#: Files whose content defines a run's configuration.
CONFIG_FILES: tuple[str, ...] = (
    "config/config.yaml",
    "config/cell_lines.yaml",
    "config/ccle_depmap_ids.yaml",
)

#: Dependencies worth pinning in the record. Exact versions live in
#: `pyproject.toml`; what matters here is what was actually importable, because
#: a drifted environment produces different numbers from the same code.
TRACKED_PACKAGES: tuple[str, ...] = (
    "snakemake",
    "pysam",
    "pyBigWig",
    "hic-straw",
    "pandas",
    "pydantic",
    "requests",
    "numpy",
    "scipy",
)

#: Verdicts for whether the recorded commit could be the producer.
CANDIDATE = "head_is_a_candidate_producer"
IMPOSSIBLE = "head_cannot_have_produced_this_run"
UNDETERMINED = "undetermined_dirty_worktree"


def sha256_file(path: Path) -> str:
    """Hash a file's bytes.

    Args:
        path: File to read.

    Returns:
        Lower-case hex digest, prefixed with the algorithm.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _git(args: list[str], repo_root: Path) -> str | None:
    """Run a git command, returning None when it cannot be answered.

    Args:
        args: Arguments after ``git``.
        repo_root: Repository root.

    Returns:
        Stripped stdout, or None on any failure.
    """
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def code_state(repo_root: Path) -> dict[str, Any]:
    """Describe the repository at the moment of writing.

    A failure to read git is reported as ``None``, never as a plausible-looking
    default: a manifest that silently claims a clean worktree it could not
    check would be worse than one that admits it does not know (invariant 2).

    Args:
        repo_root: Repository root.

    Returns:
        Commit, commit time, dirtiness and the dirty paths.
    """
    head = _git(["rev-parse", "HEAD"], repo_root)
    committed_at = _git(["log", "-1", "--format=%cI"], repo_root)
    porcelain = _git(["status", "--porcelain"], repo_root)
    dirty_paths = (
        sorted(line[3:] for line in porcelain.splitlines() if line.strip())
        if porcelain is not None
        else None
    )
    return {
        "head_commit": head,
        "head_committed_at": committed_at,
        "worktree_clean": None if dirty_paths is None else not dirty_paths,
        "dirty_paths": dirty_paths,
    }


def head_consistency(
    code: dict[str, Any], output_mtimes: list[float]
) -> dict[str, Any]:
    """Decide whether the recorded commit could have produced these outputs.

    This is a **bound, not an attestation**. If every output was written after
    HEAD was committed, HEAD is merely a candidate; if any output predates the
    commit, HEAD definitely did not produce the run. A dirty worktree makes the
    question unanswerable, because the code that ran was never committed.

    Args:
        code: Result of :func:`code_state`.
        output_mtimes: POSIX mtimes of the run's output files.

    Returns:
        The verdict plus the comparison it rests on.
    """
    committed_at = code.get("head_committed_at")
    clean = code.get("worktree_clean")
    if not committed_at or not output_mtimes:
        return {
            "verdict": UNDETERMINED,
            "reason": "HEAD commit time or run outputs could not be read",
        }
    commit_ts = datetime.fromisoformat(committed_at).timestamp()
    oldest = min(output_mtimes)
    if oldest < commit_ts:
        return {
            "verdict": IMPOSSIBLE,
            "reason": (
                "an output predates the recorded commit, so the run was "
                "produced by earlier code"
            ),
            "oldest_output_at": datetime.fromtimestamp(oldest, UTC).isoformat(),
            "head_committed_at": committed_at,
        }
    if clean is not True:
        return {
            "verdict": UNDETERMINED,
            "reason": (
                "the worktree was not clean, so the code that ran is not the "
                "code any commit records"
            ),
        }
    return {
        "verdict": CANDIDATE,
        "reason": (
            "every output was written after the recorded commit and the "
            "worktree was clean — a bound, not proof of production"
        ),
        "oldest_output_at": datetime.fromtimestamp(oldest, UTC).isoformat(),
        "head_committed_at": committed_at,
    }


def config_fingerprint(repo_root: Path) -> dict[str, str | None]:
    """Hash each configuration file.

    Args:
        repo_root: Repository root.

    Returns:
        Path to digest, with None for a file that is absent.
    """
    out: dict[str, str | None] = {}
    for rel in CONFIG_FILES:
        path = repo_root / rel
        out[rel] = sha256_file(path) if path.is_file() else None
    return out


def environment() -> dict[str, Any]:
    """Record the interpreter and the installed versions of tracked packages.

    Returns:
        Python version and a package-to-version mapping, with None where a
        package is not installed.
    """
    import sys

    versions: dict[str, str | None] = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": ".".join(str(n) for n in sys.version_info[:3]),
        "packages": versions,
    }


def external_data(repo_root: Path) -> dict[str, Any]:
    """Read the machine-downloaded data manifest.

    Args:
        repo_root: Repository root.

    Returns:
        The parsed manifest, or a note explaining why it could not be read.
    """
    path = repo_root / "data" / "external" / "manifest.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"unreadable": str(exc)}
    if not isinstance(loaded, dict):
        return {"unreadable": f"expected a mapping, got {type(loaded).__name__}"}
    return loaded


def output_inventory(run_dir: Path) -> tuple[dict[str, Any], list[float]]:
    """Hash every result file in a run directory.

    The hashes are the part of a manifest that holds regardless of provenance:
    they make a later hand-edit of a result detectable, which invariant 1 calls
    the difference between fixing a result and fabricating one.

    Args:
        run_dir: Directory holding one run's outputs.

    Returns:
        A ``(inventory, mtimes)`` pair; the manifest itself is excluded.
    """
    inventory: dict[str, Any] = {}
    mtimes: list[float] = []
    for path in sorted(run_dir.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        stat = path.stat()
        mtimes.append(stat.st_mtime)
        inventory[path.name] = {
            "sha256": sha256_file(path).removeprefix("sha256:"),
            "bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        }
    return inventory, mtimes


def snakemake_state(run_dir: Path, repo_root: Path) -> dict[str, Any]:
    """Report which of this run's outputs Snakemake considers unfinished.

    Snakemake records an interrupted job by writing a marker whose filename is
    the base64 of the output path. Nothing in the repository surfaced those
    markers, so an interrupted run was indistinguishable from a finished one —
    ``results/MYC_K562`` carried such a marker and no file said so. "Is this
    run complete?" is part of provenance, so the manifest answers it.

    A marker means *the job was interrupted*, not necessarily that the bytes
    are truncated: a write can finish before the process is killed. The
    manifest therefore reports the marker and leaves the content question to
    whoever reads the hashes.

    Args:
        run_dir: Directory holding one run's outputs.
        repo_root: Repository root.

    Returns:
        The marked outputs belonging to this run, or a note if unreadable.
    """
    import base64

    marker_dir = repo_root / ".snakemake" / "incomplete"
    if not marker_dir.is_dir():
        return {"incomplete_outputs": [], "note": "no incomplete markers on disk"}
    marked: list[str] = []
    for marker in sorted(marker_dir.iterdir()):
        try:
            decoded = base64.b64decode(marker.name).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        candidate = Path(decoded)
        # The manifest's own marker is live while this very job runs, so
        # including it would make every manifest report itself as unfinished.
        if candidate.name == "manifest.json":
            continue
        # Compare resolved parents, not directory names. An isolated run under
        # `results_dir` elsewhere on disk has the same leaf name — a marker
        # left by `/tmp/.../scratchpad/c3/results/VEGFA_HeLa/` was reported
        # against the repository's own `results/VEGFA_HeLa/` until this
        # compared full paths.
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        try:
            same = candidate.parent.resolve() == run_dir.resolve()
        except OSError:  # pragma: no cover - unresolvable path
            same = False
        if same:
            marked.append(decoded)
    return {
        "incomplete_outputs": marked,
        "note": (
            "A marker means the producing job was interrupted. The bytes may "
            "still be complete — compare against the recorded hash."
        ),
    }


#: Modules whose use makes a run non-reproducible without a recorded seed.
#: Written as data rather than as a regular expression because the probe walks
#: the AST: these are matched against *imports*, never against text, so a
#: docstring or a string constant naming them is not a finding (roadmap H24).
_STOCHASTIC_MODULES: frozenset[str] = frozenset(
    {"random", "secrets", "numpy.random", "numpy.random.mtrand"}
)
#: Names that mean sampling wherever they come from. `default_rng` is here
#: because the textual probe this replaced could not see it at all: neither
#: `rng = default_rng()` nor `import random as rnd` matched its patterns, so a
#: module that genuinely sampled would have been reported as clean.
_STOCHASTIC_NAMES: frozenset[str] = frozenset({"default_rng", "urandom"})


class _RandomnessVisitor(ast.NodeVisitor):
    """Collect the imports and calls that make a module stochastic.

    Anchored on the import graph rather than on spelling: an alias is followed
    (`import random as rnd`), a bare name brought in from a stochastic module
    is followed (`from random import shuffle`), and anything that is only a
    string or a comment is invisible because the parser already discarded it.
    """

    def __init__(self) -> None:
        self.findings: list[dict[str, Any]] = []
        #: local alias → the stochastic module it refers to
        self._aliases: dict[str, str] = {}
        #: local name → the stochastic module it was imported from
        self._imported: dict[str, str] = {}

    # -- imports ----------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".")[0]
            if alias.name in _STOCHASTIC_MODULES or root in _STOCHASTIC_MODULES:
                local = alias.asname or alias.name.split(".")[0]
                self._aliases[local] = alias.name
                self._record(node, f"import {alias.name}")
            elif alias.name in {"numpy", "os"}:
                # Not stochastic in itself; remembered so that `np.random.*`
                # and `os.urandom(...)` can be resolved below.
                self._aliases[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        root = module.split(".")[0]
        for alias in node.names:
            local = alias.asname or alias.name
            stochastic_module = (
                module in _STOCHASTIC_MODULES or root in _STOCHASTIC_MODULES
            )
            if stochastic_module or alias.name in _STOCHASTIC_NAMES:
                self._imported[local] = module or "?"
                self._record(node, f"from {module} import {alias.name}")
            elif alias.name == "random" and root in {"numpy", "np"}:
                self._aliases[local] = "numpy.random"
                self._record(node, f"from {module} import {alias.name}")
        self.generic_visit(node)

    # -- calls and attribute chains ---------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        chain = _attribute_chain(node.func)
        if chain and self._is_stochastic(chain):
            self._record(node, ".".join(chain) if len(chain) > 1 else f"{chain[0]}()")
        self.generic_visit(node)

    def _is_stochastic(self, chain: list[str]) -> bool:
        """Does this call chain resolve to sampling?

        Args:
            chain: Flattened attribute chain, e.g. ``["np", "random", "normal"]``.

        Returns:
            True when the chain's head is a local alias of a stochastic module,
            or is ``numpy``/``os`` followed by the stochastic attribute, or is a
            bare name imported from such a module.
        """
        head, rest = chain[0], chain[1:]
        resolved = self._aliases.get(head)
        if resolved in _STOCHASTIC_MODULES:
            return True
        if resolved == "numpy" and rest and rest[0] == "random":
            # `numpy` itself is not stochastic, only this attribute of it.
            return True
        if resolved == "os" and rest and rest[0] in _STOCHASTIC_NAMES:
            return True
        return len(chain) == 1 and (
            head in self._imported or head in _STOCHASTIC_NAMES
        )

    def _record(self, node: ast.AST, construct: str) -> None:
        self.findings.append(
            {"line": getattr(node, "lineno", 0), "construct": construct}
        )


def _attribute_chain(node: ast.AST) -> list[str]:
    """Flatten ``a.b.c`` into ``["a", "b", "c"]``; ``[]`` if not a plain chain."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return []


def randomness_findings(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Find every stochastic construct in ``paths``, by parsing them.

    Args:
        paths: Python files to inspect.

    Returns:
        One record per finding, sorted by ``(file, line, construct)`` so that
        two runs over the same tree produce byte-identical provenance. A file
        that cannot be parsed yields a finding of its own rather than being
        skipped: unreadable is unknown, not clean (invariant 2).
    """
    findings: list[dict[str, Any]] = []
    for path in paths:
        name = str(path)
        try:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=name)
        except (OSError, SyntaxError, ValueError) as exc:
            findings.append(
                {"file": name, "line": 1, "construct": f"unparseable: {exc}"}
            )
            continue
        visitor = _RandomnessVisitor()
        visitor.visit(tree)
        for finding in visitor.findings:
            findings.append({"file": name, **finding})
    return sorted(findings, key=lambda f: (f["file"], f["line"], f["construct"]))


def stochastic_components(repo_root: Path) -> dict[str, Any]:
    """State whether the pipeline has any randomness, with its evidence.

    ⚠️ Roadmap `H24`. This used to be a textual ``git grep``, and both
    directions of that were wrong. It went red for `B11c`'s ``_chance_hits``,
    a closed-form expectation that samples nothing, because the *docstring*
    described a shuffled null — and the fix at the time was to reword the
    prose, i.e. the record was being written to fit the detector. The
    dangerous direction was the other one: ``rng = default_rng()`` and
    ``import random as rnd`` matched none of its patterns, so a module that
    genuinely sampled would have been reported clean while the manifest
    claimed reproducibility it could not support.

    The walk is over the AST of every tracked ``src/**.py``, so comments and
    string constants are structurally invisible — which is also why this
    module no longer has to exempt its own source.

    Args:
        repo_root: Repository root.

    Returns:
        The claim, the constructs behind it, how many files were read, and how.
    """
    listing = _git(["ls-files", "--", "src/*.py"], repo_root)
    files = [
        repo_root / line
        for line in (listing or "").splitlines()
        if line.strip().endswith(".py")
    ]
    findings = randomness_findings(files)
    for finding in findings:
        with suppress(ValueError):
            finding["file"] = str(Path(finding["file"]).relative_to(repo_root))
    return {
        "present": bool(findings),
        "files": sorted({finding["file"] for finding in findings}),
        "findings": findings,
        "scanned": len(files),
        "evidence": (
            "ast.parse over every tracked src/**.py; imports of "
            "random/secrets/numpy.random, plus default_rng and os.urandom "
            "calls, resolved through their local aliases. Comments and string "
            "constants are not matched (roadmap H24)."
        ),
        "note": (
            "No seeds are recorded because no stochastic component was found. "
            "An empty seeds map would advertise bookkeeping that tracks nothing."
        ),
    }


def data_sources(repo_root: Path) -> dict[str, Any]:
    """Which release of each versioned remote source this run reads.

    `external_data` records the **bytes on disk** and their digests. This
    records the ones that are not on disk: a live API answers with whatever
    release it is serving, so the only provenance available is the release the
    configuration pinned and whether the host confirmed it.

    It exists because the manifest fingerprinted code and config and recorded
    no source release at all, while the cache was quietly holding cDNA from
    two Ensembl releases at once (roadmap B17). A run that cannot name its
    annotation release cannot be reproduced and, worse, cannot be *compared*
    with another run.

    Args:
        repo_root: Repository root.

    Returns:
        One block per versioned remote source. ``release_verified: false``
        means the host was not asked — the manifest never implies a check it
        did not perform.
    """
    import yaml

    try:
        raw = (
            yaml.safe_load(
                (repo_root / "config" / "config.yaml").read_text(encoding="utf-8")
            )
            or {}
        )
    except (OSError, yaml.YAMLError):
        return {"ensembl": {"release": None, "reason": "config unreadable"}}
    base_url = str(raw.get("ensembl_base_url", ""))
    declared = raw.get("ensembl_release")
    return {"ensembl": ensembl_release.describe(base_url, declared, check=False)}

def build_manifest(run_dir: Path, repo_root: Path) -> dict[str, Any]:
    """Assemble the full provenance record for one run directory.

    Args:
        run_dir: Directory holding one run's outputs.
        repo_root: Repository root.

    Returns:
        The manifest, ready to serialise.
    """
    inventory, mtimes = output_inventory(run_dir)
    code = code_state(repo_root)
    gene, _, cell_line = run_dir.name.partition("_")
    return {
        "schema_version": SCHEMA_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
        "run": {"gene": gene, "cell_line": cell_line, "dir": run_dir.name},
        "code": code,
        "head_consistency": head_consistency(code, mtimes),
        "config": config_fingerprint(repo_root),
        "external_data": external_data(repo_root),
        "data_sources": data_sources(repo_root),
        "environment": environment(),
        "snakemake_state": snakemake_state(run_dir, repo_root),
        "stochastic_components": stochastic_components(repo_root),
        "outputs": inventory,
    }
