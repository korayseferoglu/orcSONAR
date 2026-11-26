"""The SessionStart status line must be true, or say it does not know.

Roadmap item H4. The hook prints six things at launch: phase, next item,
pre-registration lock, uncommitted file count, ruff/mypy, last null-gate
result. Every one of them is a claim about the project, so each is pinned here.

Two failure types this file exists to catch, both of which have already
happened in this repo:

* **The instrument is dead and nobody notices.** `log-instructions-loaded.py`
  was committed `100644`; the shell could not execute it, the launch event
  died with `exit 126`, and the log stayed empty for a session while the
  roadmap recorded the hook as installed. `test_settings_hooks_are_executable`
  generalises that over every hook `settings.json` actually invokes — on disk
  *and* in the git index, because the mode is what gets committed.
* **A failed measurement reads as a clean one** (invariant 2: absence of data
  must never look safer). `ruff_text`/`mypy_text` are therefore tested on the
  tool-missing and tool-crashed paths, not only the happy one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"

sys.path.insert(0, str(HOOKS))

import _status  # noqa: E402, I001


# --------------------------------------------------------------------------
# the instrument itself
# --------------------------------------------------------------------------


def _settings_commands() -> list[str]:
    """Every shell command `settings.json` wires to a hook event."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    found: list[str] = []
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = hook.get("command")
                if isinstance(command, str):
                    found.append(command)
    return found


def _hook_paths() -> list[Path]:
    """Resolve the hook scripts those commands point at."""
    paths = []
    for command in _settings_commands():
        raw = command.strip().strip('"').replace("${CLAUDE_PROJECT_DIR:-.}", str(ROOT))
        candidate = Path(raw)
        if candidate.suffix == ".py":
            paths.append(candidate)
    return paths


def test_settings_wires_the_session_status_hook() -> None:
    """H4 is only done if the launch event actually calls the script."""
    names = {path.name for path in _hook_paths()}
    assert "session-status.py" in names, "SessionStart hook is not wired in settings.json"


@pytest.mark.parametrize("path", _hook_paths(), ids=lambda p: p.name)
def test_settings_hooks_are_executable(path: Path) -> None:
    """A hook without the exec bit fails `exit 126` and is silently skipped."""
    assert path.is_file(), f"{path} is wired in settings.json but does not exist"
    assert os.access(path, os.X_OK), f"{path.name} is not executable: shell would exit 126"

    rel = path.relative_to(ROOT)
    out = subprocess.run(
        ["git", "ls-files", "-s", "--", str(rel)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert out.strip(), f"{rel} is not tracked by git (invariant 4: uncommitted is nothing)"
    assert out.split()[0] == "100755", f"{rel} is committed {out.split()[0]}, not 100755"


# --------------------------------------------------------------------------
# roadmap parsing
# --------------------------------------------------------------------------

FIXTURE = """
### FAZ 0 — Harness

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **H1** | Dizin sözleşmesi | — | `pytest tests/hooks/` yeşil | **DONE** |
| **H2** | Kurallar | H1 | log üç dosyayı gösteriyor | **DONE** |
| **H4** | SessionStart | H2 | durum basılıyor | TODO |
| **H5** | skill'ler | H4 | üçü de çalışıyor | TODO |
| **H8** | Ön kayıt kilidi | — | edit reddediliyor | TODO |
| *(CI)* | CI kurulumu `H6`'dadır | — | — | — |

### FAZ G — Yayın

| id | iş | bağımlılık | durum |
|---|---|---|---|
| **G1** | Preprint | H8 | TODO |
| **E6** | *(madde değil)* tartışmaya | G1 | — |
"""


@pytest.fixture
def items() -> list[_status.Item]:
    """The fixture roadmap, parsed."""
    return _status.parse_roadmap(FIXTURE)


def test_parses_ids_phases_and_status(items: list[_status.Item]) -> None:
    """Ids, their phase heading and the status alphabet all come through."""
    by_id = {item.id: item for item in items}
    assert set(by_id) == {"H1", "H2", "H4", "H5", "H8", "G1", "E6"}
    assert by_id["H1"].status == "DONE"
    assert by_id["H4"].status == "TODO"
    assert by_id["H4"].phase.startswith("FAZ 0")
    assert by_id["G1"].phase.startswith("FAZ G")


def test_four_column_table_still_yields_status_and_deps(items: list[_status.Item]) -> None:
    """FAZ G has no acceptance column; status is the last cell either way."""
    by_id = {item.id: item for item in items}
    assert by_id["G1"].status == "TODO"
    assert by_id["G1"].deps == ["H8"]
    assert by_id["E6"].status == "—"


def test_dependency_em_dash_means_no_dependency(items: list[_status.Item]) -> None:
    """`—` in the dependency cell is none, not an item called em-dash."""
    by_id = {item.id: item for item in items}
    assert by_id["H1"].deps == []
    assert by_id["H2"].deps == ["H1"]


def test_next_item_is_the_first_todo_whose_deps_are_done(items: list[_status.Item]) -> None:
    """H4 is ready (H2 DONE); H5 is not (H4 TODO); H8 is ready but later."""
    ready = _status.ready_items(items)
    assert [item.id for item in ready] == ["H4", "H8"]
    assert _status.next_item(items).id == "H4"


def test_unknown_dependency_is_not_treated_as_met() -> None:
    """A typo'd dependency must block, not silently promote an item."""
    text = FIXTURE.replace("| **H4** | SessionStart | H2 |", "| **H4** | SessionStart | H99 |")
    ready = _status.ready_items(_status.parse_roadmap(text))
    assert [item.id for item in ready] == ["H8"]


def test_real_roadmap_parses_and_h4_is_the_next_item() -> None:
    """The live roadmap, not a fixture: the hook has to read that file."""
    text = (ROOT / "SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
    items = _status.parse_roadmap(text)
    by_id = {item.id: item for item in items}
    assert len(items) > 50, "the roadmap has 60+ items; the parser lost most of them"
    for done in ("H1", "H2", "H3"):
        assert by_id[done].status == "DONE"
    assert by_id["D1"].deps == ["D0"]


# --------------------------------------------------------------------------
# failure direction: a measurement that did not happen says so
# --------------------------------------------------------------------------


def test_ruff_text_reports_clean_only_after_a_real_run() -> None:
    """Exit 0 from a real ruff is the only thing allowed to read as clean."""
    assert "temiz" in _status.ruff_text(found=True, returncode=0, output="All checks passed!")


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"found": False, "returncode": None, "output": ""}, "ruff not installed"),
        ({"found": True, "returncode": None, "output": "timeout"}, "ruff could not run"),
    ],
)
def test_ruff_text_never_reads_clean_when_it_did_not_run(kwargs: dict, why: str) -> None:
    """Invariant 2: absence of a measurement must not look like a pass."""
    text = _status.ruff_text(**kwargs)
    assert _status.NOT_MEASURED in text, why
    assert "temiz" not in text, why


def test_ruff_text_counts_findings() -> None:
    """A failing run reports how many, so the number can be watched."""
    output = "src/a.py:1:1: F401 unused\nsrc/b.py:2:1: I001 unsorted\nFound 2 errors."
    assert "2" in _status.ruff_text(found=True, returncode=1, output=output)


def test_mypy_text_uses_the_reported_error_count() -> None:
    """mypy prints its own total; do not recount it from the lines."""
    text = _status.mypy_text(found=True, returncode=1, output="Found 72 errors in 35 files")
    assert "72" in text


def test_mypy_text_never_reads_clean_when_it_did_not_run() -> None:
    """Same direction rule as ruff."""
    text = _status.mypy_text(found=False, returncode=None, output="")
    assert _status.NOT_MEASURED in text
    assert "temiz" not in text


# --------------------------------------------------------------------------
# pre-registration lock (invariant 6) and the null gate (E1)
# --------------------------------------------------------------------------


def test_prereg_text_says_missing_when_there_is_no_file() -> None:
    """Today's true state: the document does not exist yet."""
    text = _status.prereg_text(exists=False, committed=None, a12_status="TODO", enforced=False)
    assert "yok" in text


def test_prereg_text_distinguishes_locked_from_merely_committed() -> None:
    """A12 committed is the lock; the hook (H8) is what enforces it."""
    unlocked = _status.prereg_text(exists=True, committed="abc1234", a12_status="TODO", enforced=False)
    locked = _status.prereg_text(exists=True, committed="abc1234", a12_status="DONE", enforced=True)
    assert "KİLİTLİ" not in unlocked
    assert "KİLİTLİ" in locked


def test_prereg_text_flags_a_lock_that_nothing_enforces() -> None:
    """Invariant 3: a lock declared in a document is not a lock."""
    text = _status.prereg_text(exists=True, committed="abc1234", a12_status="DONE", enforced=False)
    assert "H8" in text, "an unenforced lock must name the item that would enforce it"


def test_null_gate_text_says_never_run_when_no_artifact_exists() -> None:
    """E1 has not run; saying nothing would read as nothing wrong."""
    text = _status.null_gate_text(path=None, payload=None)
    assert "E1" in text


def test_null_gate_text_surfaces_the_verdict_it_finds() -> None:
    """When the gate has run, its own numbers are what gets printed."""
    text = _status.null_gate_text(
        path="reports/null_gate.json",
        payload={"at": "2026-12-01T10:00:00+00:00", "p_value": 0.47, "significant": 0},
    )
    assert "0.47" in text


# --------------------------------------------------------------------------
# the hook end to end
# --------------------------------------------------------------------------


def _run_hook(stdin: str) -> subprocess.CompletedProcess[str]:
    """Run the real hook the way Claude Code runs it."""
    return subprocess.run(
        [sys.executable, "-I", str(HOOKS / "session-status.py")],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )


@pytest.mark.parametrize(
    "label",
    ["faz", "sıradaki", "ön kayıt", "commit'siz", "ruff", "mypy", "null kapısı"],
)
def test_hook_prints_every_required_section(label: str) -> None:
    """The six things H4 promises, printed at launch."""
    proc = _run_hook(json.dumps({"hook_event_name": "SessionStart", "source": "startup"}))
    assert proc.returncode == 0, proc.stderr
    assert label in proc.stdout, f"missing section: {label}\n{proc.stdout}"


def test_every_roadmap_row_has_exactly_the_expected_columns() -> None:
    """An unescaped `|` inside a cell silently shifts every column after it.

    Measured while adding `B2a`: the text `float | None` split the work cell in
    two, so the parser read part of the prose as the dependency list and
    returned `['B2', 'B1', 'H6', 'B8', 'B2']` — all real item ids, so nothing
    downstream could notice. The queue's order is computed from that column,
    which makes this a correctness problem, not a formatting one. Pipes inside
    a cell have to be written `\\|`.
    """
    text = (ROOT / "SCIENTIFIC_ROADMAP.md").read_text(encoding="utf-8")
    bad: list[str] = []
    for line in text.splitlines():
        if not re.match(r"^\|\s*\*\*[A-Z]\d+[a-z]?\*\*\s*\|", line):
            continue
        cells = line.replace(r"\|", "\0").split("|")
        # A five-column row splits into: leading "", id, work, deps, criterion,
        # status, trailing "". FAZ G's four-column table drops the criterion.
        if len(cells) not in (6, 7):
            bad.append(f"{line.split('|')[1].strip()}: {len(cells) - 2} cells")
    assert not bad, f"rows with unescaped pipes: {bad}"


def _session_status() -> object:
    """Import the hyphenated hook script as a module."""
    spec = importlib.util.spec_from_file_location("session_status", HOOKS / "session-status.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_git_keeps_the_porcelain_status_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """`git status --porcelain` writes ` M path`; trimming that pad trims a letter.

    An unstaged change has a blank first status column, so a whole-output
    ``strip()`` shifts the line left and ``line[3:]`` then starts inside the
    filename. The collector and the wording function are each correct alone —
    the loss happens at the seam, which is why no existing test saw it.
    """
    module = _session_status()
    monkeypatch.setattr(module, "run", lambda args, timeout: (0, " M SCIENTIFIC_ROADMAP.md\n"))
    assert module.git("status", "--porcelain") == " M SCIENTIFIC_ROADMAP.md"


def test_unstaged_file_is_named_in_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other end of the seam: invariant 4's line must name the real file."""
    module = _session_status()
    monkeypatch.setattr(module, "run", lambda args, timeout: (0, " M SCIENTIFIC_ROADMAP.md\n"))
    line = _status.uncommitted_text(module.git("status", "--porcelain"))
    assert "SCIENTIFIC_ROADMAP.md" in line, line


def test_the_block_reports_the_pre_registration_lock_as_enforced() -> None:
    """H8 is installed, so the one screen every session reads must say so.

    The detector originally grepped settings.json for the literal string
    "PRE_REGISTRATION", which is how the roadmap *described* the planned hook
    (`if: "Edit(docs/PRE_REGISTRATION.md)"`). The hook that was actually built
    is a script that resolves the path itself, so the detector kept reporting
    "yaptırım: H8 kurulmadı" after H8 shipped — looking for the shape of a
    declaration instead of for the thing being true.
    """
    proc = _run_hook(json.dumps({"hook_event_name": "SessionStart", "source": "startup"}))
    assert proc.returncode == 0, proc.stderr
    assert "yaptırım: H8 kurulu" in proc.stdout, proc.stdout


def test_hook_exits_zero_on_a_garbage_payload() -> None:
    """A status line must never be able to wedge a session start."""
    proc = _run_hook("not json at all")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), "a broken payload still deserves a status line"


# ---------------------------------------------------------------------------
# The phase breakdown must account for every item (roadmap H11)
# ---------------------------------------------------------------------------

_THIRD_STATE = """## FAZ X — Deneme

| id | iş | bağımlılık | kabul kriteri | durum |
|---|---|---|---|---|
| **X1** | bir | — | k | **DONE** |
| **X2** | iki | — | k | TODO |
| **X3** | üç | — | k | BLOCKED(kullanıcı kararı) |
| **X4** | dört | — | k | DOING |
"""


def test_the_breakdown_sums_to_the_total(items: list[_status.Item]) -> None:
    """Every item is in exactly one bucket, in every phase.

    The old line printed `len(in_phase)` as the total while counting only
    `DONE` and `TODO`, so a third state went missing without the arithmetic
    looking wrong. Deriving the counts by partition makes that impossible.
    """
    for phase in {item.phase for item in items}:
        in_phase = [item for item in items if item.phase == phase]
        breakdown = _status.status_breakdown(in_phase)
        counted = sum(int(part.split()[0]) for part in breakdown.split(", "))
        assert counted == len(in_phase), f"{phase}: {breakdown}"


def test_a_blocked_item_is_visible() -> None:
    """The case that actually bit: a BLOCKED item vanished from the launch line.

    It is the one state that never advances on its own — it is waiting on a
    person — so losing it loses the only item nobody will be reminded about.
    """
    parsed = _status.parse_roadmap(_THIRD_STATE)
    breakdown = _status.status_breakdown(parsed)
    assert "1 BLOCKED(kullanıcı kararı)" in breakdown
    assert "1 DOING" in breakdown
    assert "1 DONE" in breakdown
    assert "1 TODO" in breakdown


def test_a_malformed_status_is_loud_not_silently_blank() -> None:
    """A bare `BLOCKED` is malformed, and used to disappear.

    The convention is `BLOCKED(<reason>)` — a blocked item must say what it
    waits for. The bare word matched nothing, became `—`, and then fell out of
    a line that counted only DONE and TODO. Two defects stacked: the parser
    erased the text, and the counter dropped the bucket. It now keeps the text
    behind a `?` so the cell reads as broken rather than empty.
    """
    parsed = _status.parse_roadmap(
        "### FAZ Y — Deneme\n\n"
        "| id | iş | bağımlılık | kabul kriteri | durum |\n"
        "|---|---|---|---|---|\n"
        "| **Y1** | bir | — | k | BLOCKED |\n"
    )
    assert [item.status for item in parsed] == ["?BLOCKED"]
    assert "1 ?BLOCKED" in _status.status_breakdown(parsed)


def test_a_row_with_no_status_cell_stays_dash() -> None:
    """An intentionally statusless row must stay distinguishable from a typo."""
    parsed = _status.parse_roadmap(
        "### FAZ Z — Deneme\n\n"
        "| id | iş | bağımlılık | durum |\n"
        "|---|---|---|---|\n"
        "| **Z1** | *(madde değil)* not | — | — |\n"
    )
    assert [item.status for item in parsed] == ["—"]


def test_done_comes_first_then_todo_then_the_rest() -> None:
    """A stable order, so the line reads the same way every session."""
    parsed = _status.parse_roadmap(_THIRD_STATE)
    breakdown = _status.status_breakdown(parsed)
    assert breakdown.startswith("1 DONE, 1 TODO")


def test_a_statusless_row_is_labelled_not_hidden(
    items: list[_status.Item],
) -> None:
    """`E6` carries "—" because its row says "(madde değil)".

    Dropping it would be the very bug this function prevents, so it is named.
    """
    faz_g = [item for item in items if item.phase and "FAZ G" in item.phase]
    assert faz_g, "fixture'da FAZ G yok"
    assert "durumsuz" in _status.status_breakdown(faz_g)


# ---------------------------------------------------------------------------
# The instructions-loaded log has to be read, not just written (roadmap H13)
# ---------------------------------------------------------------------------

_LOG = (
    '{"at": "2026-11-26T17:35:22+00:00", '
    '"file_path": "/repo/.claude/rules/00-degismezler.md"}\n'
    '{"at": "2026-11-26T18:58:01+00:00", '
    '"file_path": "/repo/.claude/rules/20-skor-degismezleri.md"}\n'
)


def test_a_rule_that_never_loaded_is_loud() -> None:
    """The dead-instrument case, and the only one worth interrupting for.

    A `paths:` glob that never fires means the rule's content has never been in
    context, while the roadmap records the rule as installed. H4 wrote this log
    precisely so that gap is observable; reporting it is what makes the log an
    instrument rather than a file.
    """
    text = _status.instructions_text(
        _LOG,
        ["00-degismezler.md", "10-koordinatlar.md", "20-skor-degismezleri.md"],
    )
    assert "2/3" in text
    assert "10-koordinatlar.md" in text
    assert "HİÇ yüklenmeyen" in text


def test_all_rules_loaded_reports_the_count_and_the_last_time() -> None:
    """The quiet case still says how much it checked."""
    text = _status.instructions_text(
        _LOG, ["00-degismezler.md", "20-skor-degismezleri.md"]
    )
    assert "2/2" in text
    assert "HİÇ yüklenmeyen" not in text
    assert "2026-11-26" in text


def test_an_unreadable_log_says_so_rather_than_claiming_nothing_loaded() -> None:
    """Invariant 2's direction: cannot measure is not the same as measured zero.

    Reporting "0/3 loaded" for a missing log would raise a false alarm every
    time the file is absent, and an alarm that cries wolf gets ignored — which
    is how the real dead instrument would then slip past.
    """
    text = _status.instructions_text(None, ["00-degismezler.md"])
    assert "okunamadı" in text
    assert "0/" not in text


def test_a_corrupt_line_is_skipped_not_fatal() -> None:
    """One bad line must not blind the whole summary."""
    text = _status.instructions_text(
        "not json\n" + _LOG, ["00-degismezler.md", "20-skor-degismezleri.md"]
    )
    assert "2/2" in text


def test_no_rule_files_is_reported_as_such() -> None:
    """An empty rules directory is a finding, not a pass."""
    assert "kural dosyası yok" in _status.instructions_text(_LOG, [])
