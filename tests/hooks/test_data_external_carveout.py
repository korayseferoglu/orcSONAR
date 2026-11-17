"""The data/external/ carve-out must cut exactly where the convention says.

`data/` is hand-curated reference data and the guards refuse every write to it.
`data/external/` is the one exception: machine-downloaded, re-downloadable,
checksummed in its manifest. The split is roadmap item H1, and it exists so the
sandbox rule (H12) does not have to be switched off the week the GENCODE
download lands (D0) — a rule declared and then disabled is worse than no rule.

A carve-out that lets something through by accident is worse than no carve-out,
so the prefix trap and the ``..`` escape are pinned here rather than trusted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"

ALLOW = 0
BLOCK = 2


def _run(hook: str, payload: dict) -> int:
    """Feed a hook its stdin payload and return its exit code."""
    proc = subprocess.run(
        [sys.executable, "-I", str(HOOKS / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode


@pytest.mark.parametrize(
    ("path", "expected", "why"),
    [
        ("data/external/manifest.json", ALLOW, "the manifest itself is written here"),
        ("data/external/gencode/x.gtf.gz", ALLOW, "nested paths are still inside"),
        ("data/cache/orcsonar_cache.db", BLOCK, "the SQLite cache is curated data"),
        ("data/2_Varyant_Toksisite/cosmic.vcf", BLOCK, "licence-gated, not re-downloadable"),
        ("data/externalEVIL/x", BLOCK, "prefix trap: externalEVIL is not external"),
        ("data/external/../leak.txt", BLOCK, "`..` must not escape the writable area"),
        ("results/VEGFA_HeLa/stage7_scores.json", ALLOW, "results/ is a different guard's job"),
        ("src/core/models.py", ALLOW, "ordinary source file"),
    ],
)
def test_file_write_guard(path: str, expected: int, why: str) -> None:
    """Write/Edit into data/ is refused unless it lands in data/external/."""
    got = _run("block-data-writes.py", {"tool_input": {"file_path": path}})
    assert got == expected, f"{path}: {why}"


@pytest.mark.parametrize(
    ("command", "expected", "why"),
    [
        ("curl -o data/external/g.gtf.gz https://example.org/g.gtf.gz", ALLOW, "a download"),
        ("sha256sum data/external/g.gtf.gz", ALLOW, "checksumming only reads"),
        ("tee data/external/manifest.json", ALLOW, "writing the manifest"),
        ("sed -i s/x/y/ data/external/manifest.json", ALLOW, "in-place edit, allowed area"),
        ("cat data/external/manifest.json", ALLOW, "reading is never blocked"),
        ("snakemake --cores 1 results/VEGFA_HeLa/stage7_scores.json", ALLOW, "snakemake owns results/"),
        ("rm -rf data/2_Varyant_Toksisite", BLOCK, "destroying curated data"),
        ("mv data/external/a data/leak", BLOCK, "the destination leaves the writable area"),
        ("sed -i s/x/y/ data/cache/x.db", BLOCK, "in-place edit of curated data"),
        ("tee results/VEGFA_HeLa/stage7_scores.json", BLOCK, "hand-writing a result fabricates it"),
    ],
)
def test_shell_write_guard(command: str, expected: int, why: str) -> None:
    """The shell guard carves out data/external/ without opening data/."""
    got = _run("block-bash-writes.py", {"tool_input": {"command": command}})
    assert got == expected, f"{command!r}: {why}"


@pytest.mark.parametrize(
    ("command", "expected", "why"),
    [
        ("curl -o data/cache/x.db https://evil.example", BLOCK, "curl -o into curated data"),
        ("curl --output data/2_Varyant_Toksisite/c.vcf https://x", BLOCK, "long form"),
        ("curl --output-dir data/cache -o x https://x", BLOCK, "destination directory flag"),
        ("wget -O data/cache/x.db https://evil.example", BLOCK, "wget -O into curated data"),
        ("wget --output-document=data/cache/x https://x", BLOCK, "--flag=value form"),
        ("wget -P data/cache https://evil.example/x", BLOCK, "wget directory prefix"),
        ("curl -o results/VEGFA_HeLa/stage7_scores.json https://x", BLOCK, "downloading a result"),
        ("curl -o data/external/g.gtf.gz https://ftp.ebi.ac.uk/x", ALLOW, "the intended workflow"),
        ("wget -P data/external https://ftp.ebi.ac.uk/x", ALLOW, "the intended workflow"),
        ("curl -sS https://rest.ensembl.org/info/ping", ALLOW, "no destination, reads only"),
        ("curl -o /tmp/x.json https://x", ALLOW, "outside the repo"),
    ],
)
def test_downloaders_cannot_write_into_protected_dirs(
    command: str, expected: int, why: str
) -> None:
    """curl and wget were able to write anywhere until this was added.

    Found by the red-first check on the carve-out: `curl -o data/external/...`
    passed even with the carve-out disabled, which meant the guard had never
    looked at downloaders at all — `curl -o results/<run>/stage7_scores.json`
    fabricated a result unopposed. It matters more now than before, because
    with data/external/ downloading is the normal way data arrives (H1, D0).
    """
    got = _run("block-bash-writes.py", {"tool_input": {"command": command}})
    assert got == expected, f"{command!r}: {why}"


def test_guards_fail_open_on_unusable_payload() -> None:
    """A guard that crashes must not wedge the session.

    Both hooks exit 0 on anything they cannot parse, by design (`_hooklib`).
    This is a guardrail against absent-minded damage, not a security boundary.
    """
    for hook in ("block-data-writes.py", "block-bash-writes.py"):
        proc = subprocess.run(
            [sys.executable, "-I", str(HOOKS / hook)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == ALLOW, f"{hook} should fail open"


def test_manifest_is_valid_and_declares_its_schema() -> None:
    """The manifest is the record that makes a download reproducible.

    H10 (run manifest) copies these digests into each result directory, so a
    malformed manifest breaks the provenance chain rather than just this file.
    """
    manifest = HOOKS.parents[1] / "data" / "external" / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert isinstance(payload["artifacts"], list)
    for artifact in payload["artifacts"]:
        missing = {"name", "source", "sha256", "downloaded"} - set(artifact)
        assert not missing, f"{artifact.get('name', artifact)} missing {sorted(missing)}"
