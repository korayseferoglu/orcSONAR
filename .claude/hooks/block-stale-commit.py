#!/usr/bin/env python3
"""PreToolUse guard: refuse `git commit` when the test suite result is stale.

Roadmap H7. The gate measures **freshness, not running**. The full suite takes
about 3.7 minutes, and H7's own row is explicit that a gate adding that to
every commit gets bypassed — so this never runs tests. It asks one question:
has the whole suite passed *since the last change to the code being committed?*

The evidence is `reports/last-suite.json`, written by `pytest_sessionfinish` in
`tests/conftest.py`. The suite writes its own receipt rather than the gate
inferring one from a side effect, because inference does not work here:
measured, a single-file run still reports all 73 `src/` files as measured,
since `--cov=src` instruments the package whether the tests import it or not.
A receipt carries what a side effect cannot — the exit status and whether the
invocation was the whole suite or one fast file.

The row's warning about a lying gate is the thing to get right: a pytest run
from *before* an edit must not open the gate. Hence the comparison is the
receipt's timestamp against the newest mtime in the index, not merely "a
receipt exists".

`H20` amended two things that H7 got wrong in practice, both measured while
landing `H19`:

* the receipt held one record, so running any acceptance script — every one of
  them runs a narrowed pytest — erased the whole-suite evidence and refused the
  next commit. Freshness is now read from the preserved whole-suite record
  (`_receipt.whole_suite_evidence`); a narrowed run destroys no evidence.
* `pytest … && git commit …` is refused *up front*, because a `PreToolUse` hook
  sees the command before it runs. That is structural, so the gate says so in
  its own words instead of reporting a staleness it cannot distinguish.

Two deliberate non-features:

* the `src/` → `tests/` condition is a **warning**, never a refusal. The row
  says the proxy is too crude, and it is: it would block a pure refactor and
  every Phase D worktree commit.
* no escape flag. The way past this gate is to run the suite, which is the
  only thing that would make the claim true. `--no-verify` does not apply —
  that is git's own hook mechanism, not this one — and a commit made outside
  Claude Code is outside this gate entirely. That limit is real and stated
  rather than papered over.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import _receipt  # noqa: E402, I001
from _hooklib import PROJECT_ROOT, block, read_payload  # noqa: E402

# Overridable so the acceptance gate can exercise every refusal path
# against crafted receipts without overwriting the real one — a gate that
# had to clobber the receipt it depends on would be testing itself into an
# inconsistent state. The path, the schema and the merge rule all live in
# `_receipt.py`, shared with the writer in `tests/conftest.py` (H20).
RECEIPT = _receipt.receipt_path(PROJECT_ROOT)

#: Paths whose change invalidates a previous suite result.
WATCHED = ("src", "tests", "rules", "Snakefile", "config", "pyproject.toml")

_GLOBAL_FLAGS_WITH_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}


def _segments(command: str) -> list[list[str]]:
    """``command`` split into shell segments, each tokenised, in order.

    Leading ``VAR=value`` assignments are stripped so the *leading command* of
    a segment is its first token. Order is preserved because one caller needs
    to know which of two commands comes first.
    """
    out: list[list[str]] = []
    for segment in re.split(r"(?:\|\||&&|[;|&\n])", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Unbalanced quotes: fall back to a crude split rather than
            # deciding not to decide. Refusing to parse must not wave a
            # commit through.
            tokens = segment.split()
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
        out.append(tokens)
    return out


def _is_git_commit(tokens: list[str]) -> bool:
    """Whether a tokenised segment invokes git's commit subcommand."""
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
        return False
    rest = tokens[1:]
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in _GLOBAL_FLAGS_WITH_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return index < len(rest) and rest[index] == "commit"


def _is_pytest(tokens: list[str]) -> bool:
    """Whether a tokenised segment runs pytest, directly or via ``-m``."""
    if not tokens:
        return False
    head = tokens[0].rsplit("/", 1)[-1]
    if head.startswith("pytest"):
        return True
    if head.startswith("python") and "-m" in tokens:
        after = tokens[tokens.index("-m") + 1 :]
        return bool(after) and after[0] == "pytest"
    return False


def invokes_git_commit(command: str) -> bool:
    """Whether ``command`` actually runs git's commit subcommand.

    A substring search is wrong, and was measured wrong: the first version of
    this check matched an ``echo`` whose argument merely contained the words,
    and blocked the pipe-test that was exercising it — so it would also block
    ``grep "git commit" notes.md``. Each shell segment is therefore tokenised
    and only its *leading* command counts.

    Args:
        command: The shell command the tool was asked to run.

    Returns:
        True when some segment invokes the commit subcommand.
    """
    return any(_is_git_commit(tokens) for tokens in _segments(command))


def pytest_precedes_commit(command: str) -> bool:
    """Whether ``command`` runs pytest and *then* commits, in one call.

    This chain cannot work and the reason is structural: a `PreToolUse` hook
    inspects the command string **before** the command runs, so at decision
    time the receipt is still the old one. `pytest -q && git commit` is
    therefore refused even though it would have produced a fresh receipt
    seconds later.

    The limit is not fixable here — the gate cannot know that a run it has not
    seen will pass, and waiting for it would mean running the suite inside the
    hook, which is what H7 exists not to do. What *is* fixable is the message:
    the generic "receipt is stale" wording sent two sessions hunting a
    staleness bug that did not exist (roadmap H20).

    Args:
        command: The shell command the tool was asked to run.

    Returns:
        True when a pytest segment comes before a commit segment.
    """
    seen_pytest = False
    for tokens in _segments(command):
        if _is_pytest(tokens):
            seen_pytest = True
        elif _is_git_commit(tokens):
            return seen_pytest
    return False


HOW = (
    "Koş:  ~/.venvs/orcsonar/bin/python -m pytest -q\n"
    "(tam takım; ~3.7 dk. Kapı testi koşmuyor, yalnız koşulmuş olmasını ister.)"
)

CHAIN = (
    "BLOCKED: `pytest … && git commit …` tek bir komut olarak çalışmaz.\n\n"
    "Kapı komutu KOŞMADAN ÖNCE inceliyor (PreToolUse), yani karar anında makbuz\n"
    "hâlâ eski olan. Zincirin ikinci yarısı bu yüzden reddediliyor — testler\n"
    "aslında geçecek olsa bile.\n\n"
    "İki ayrı çağrı yap: önce pytest, bittikten sonra commit. Bu bir hata değil,\n"
    "koşmadan-önce-inceleyen bir kapının kaçınılmaz sonucu; burada yazılı olması\n"
    "da kapının kendisinin bir parçası (yol haritası H20).\n\n" + HOW
)


def newest_tracked_mtime() -> tuple[float, str]:
    """The newest mtime among the files git tracks in the watched paths.

    The index is the right source: a staged file is part of the commit, and an
    untracked file is not — so this is the set the commit actually carries.

    Returns:
        ``(mtime, path)``; ``(0.0, "")`` when nothing could be read.
    """
    present = [name for name in WATCHED if (Path(PROJECT_ROOT) / name).exists()]
    if not present:
        return 0.0, ""
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", *present],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=8,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 0.0, ""

    newest = 0.0
    where = ""
    for rel in listing.stdout.split("\0"):
        if not rel:
            continue
        try:
            stamp = (Path(PROJECT_ROOT) / rel).stat().st_mtime
        except OSError:
            continue
        if stamp > newest:
            newest, where = stamp, rel
    return newest, where


def src_without_tests() -> bool:
    """Whether staged changes touch `src/` but no test.

    Returns:
        True when the staged set looks like production-only change.
    """
    try:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=8,
        ).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    names = [n for n in staged if n.strip()]
    touches_src = any(n.startswith("src/") for n in names)
    touches_tests = any(n.startswith("tests/") for n in names)
    return touches_src and not touches_tests


def shown(path: Path) -> str:
    """A readable path that never raises.

    `relative_to` threw `ValueError` for a receipt outside the project — which
    is how the acceptance gate points at a temp fixture — and the crash took
    the whole hook down. A crashing `PreToolUse` hook does not refuse, it gets
    out of the way, so a cosmetic call on an error path had turned the gate
    into a no-op for exactly the case it was reporting.
    """
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


payload = read_payload()
command = str(payload.get("tool_input", {}).get("command", ""))

if not invokes_git_commit(command):
    sys.exit(0)

if pytest_precedes_commit(command):
    block(CHAIN)

# From here on the hook has decided it cares, and an unexpected error must
# **refuse** rather than get out of the way. A crashing PreToolUse hook does
# not block — it is reported and the command proceeds — so a gate that lets an
# exception escape has a hole precisely where it is least expected. This
# happened: a cosmetic `relative_to` on an error path threw ValueError and
# turned the missing-receipt case into a silent pass.
def decide() -> None:
    """Refuse the commit when the suite result cannot vouch for it."""
    try:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        block(
            "BLOCKED: test takımının sonucu yok, yani bu commit doğrulanmamış.\n\n"
            f"{shown(RECEIPT)} okunamadı — takım bu çalışma\n"
            "ağacında hiç koşmamış olabilir.\n\n" + HOW
        )

    if not isinstance(receipt, dict):
        block(f"BLOCKED: {RECEIPT.name} beklenen biçimde değil.\n\n{HOW}")

    # The latest run of any scope: a red run refuses whatever it covered.
    if int(receipt.get("exitstatus", 1)) != 0:
        block(
            "BLOCKED: en son test koşusu BAŞARISIZ bitti "
            f"(exitstatus={receipt.get('exitstatus')}, "
            f"failed={receipt.get('failed')}).\n\n"
            "Kırmızı bir takımla commit, değişmez 4'ün tersi: commit'lenmiş ama\n"
            "doğrulanmamış bir şey, hiç commit'lenmemiş olmaktan daha yanıltıcı.\n\n"
            + HOW
        )

    # Freshness is measured on the whole-suite run, which a later narrowed run
    # does not erase (H20). `None` means no whole-suite run is recorded at all.
    evidence = _receipt.whole_suite_evidence(receipt)
    if evidence is None:
        block(
            "BLOCKED: tam takım HİÇ koşmadı — makbuzda yalnız daraltılmış koşu var "
            f"({receipt.get('collected')} test, args={receipt.get('args')}).\n\n"
            "Tek bir dosyanın yeşil koşması takım hakkında kanıt değil; kapsamı\n"
            "kaydetmeyen bir kapı, depodaki en hızlı testle tatmin edilebilirdi.\n\n"
            + HOW
        )

    if int(evidence.get("exitstatus", 1)) != 0:
        block(
            "BLOCKED: en son TAM TAKIM koşusu BAŞARISIZ bitti "
            f"(exitstatus={evidence.get('exitstatus')}, "
            f"failed={evidence.get('failed')}).\n\n"
            "Sonrasında daraltılmış bir koşu yeşil olmuş olabilir, ama bir alt küme\n"
            "takımı aklamaz — kırmızı tam takım, yerine yeşil biri geçene kadar\n"
            "geçerli kanıttır.\n\n" + HOW
        )

    newest, where = newest_tracked_mtime()
    if newest and float(evidence.get("at", 0.0)) < newest:
        block(
            "BLOCKED: test sonucu BAYAT — takım koştuktan SONRA kod değişti.\n\n"
            f"en son değişen: {where}\n"
            "Bu kapının asıl işi bu: düzenlemeden önce koşulmuş bir pytest, kapıyı\n"
            "açmamalı. Açsaydı kapı 'testler geçiyor' derken aslında 'bir şeyler bir\n"
            "ara geçmişti' demiş olurdu.\n\n" + HOW
        )

    # Buradan sonrası bloke etmez. `src/` değişip test değişmemesi bir uyarı:
    # satırın dediği gibi proxy çok kaba, saf refaktörü ve Faz D worktree'lerini
    # engellerdi.
    if src_without_tests():
        json.dump(
            {
                "systemMessage": (
                    "orcSONAR: staged değişiklik `src/` içinde ama hiçbir test "
                    "dosyası değişmemiş. Uyarı, engel değil — ama değişmez 5 "
                    "testin önce kırmızı olmasını ister."
                )
            },
            sys.stdout,
        )


try:
    decide()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 - fail closed, never open
    block(
        "BLOCKED: kapı karar veremedi, o yüzden commit'i reddediyor.\n\n"
        f"beklenmeyen hata: {exc!r}\n\n"
        "Bir kapının 'bilmiyorum'u 'tamam' diye okunamaz (değişmez 2). Kapıyı\n"
        "düzelt ya da hook'u bilerek devre dışı bırak — ama sessizce geçmesin.\n\n"
        + HOW
    )
sys.exit(0)
