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
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from _hooklib import PROJECT_ROOT, block, read_payload  # noqa: E402

# Overridable so the acceptance gate can exercise every refusal path
# against crafted receipts without overwriting the real one — a gate that
# had to clobber the receipt it depends on would be testing itself into an
# inconsistent state.
RECEIPT = Path(
    os.environ.get(
        "ORCSONAR_SUITE_RECEIPT",
        str(Path(PROJECT_ROOT) / "reports" / "last-suite.json"),
    )
)

#: Paths whose change invalidates a previous suite result.
WATCHED = ("src", "tests", "rules", "Snakefile", "config", "pyproject.toml")

_GLOBAL_FLAGS_WITH_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}


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
    for segment in re.split(r"(?:\|\||&&|[;|&])", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Unbalanced quotes: fall back to a crude split rather than
            # deciding not to decide. Refusing to parse must not wave a
            # commit through.
            tokens = segment.split()
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]  # leading VAR=value assignments
        if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
            continue
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
        if index < len(rest) and rest[index] == "commit":
            return True
    return False

HOW = (
    "Koş:  ~/.venvs/orcsonar/bin/python -m pytest -q\n"
    "(tam takım; ~3.7 dk. Kapı testi koşmuyor, yalnız koşulmuş olmasını ister.)"
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

    if int(receipt.get("exitstatus", 1)) != 0:
        block(
            "BLOCKED: en son test koşusu BAŞARISIZ bitti "
            f"(exitstatus={receipt.get('exitstatus')}, "
            f"failed={receipt.get('failed')}).\n\n"
            "Kırmızı bir takımla commit, değişmez 4'ün tersi: commit'lenmiş ama\n"
            "doğrulanmamış bir şey, hiç commit'lenmemiş olmaktan daha yanıltıcı.\n\n"
            + HOW
        )

    if not receipt.get("whole_suite"):
        block(
            "BLOCKED: en son koşu tam takım değildi "
            f"({receipt.get('collected')} test, args={receipt.get('args')}).\n\n"
            "Tek bir dosyanın yeşil koşması takım hakkında kanıt değil; kapsamı\n"
            "kaydetmeyen bir kapı, depodaki en hızlı testle tatmin edilebilirdi.\n\n"
            + HOW
        )

    newest, where = newest_tracked_mtime()
    if newest and float(receipt.get("at", 0.0)) < newest:
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
