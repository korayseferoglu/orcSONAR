"""Tests for the config-key wiring check (roadmap H11).

Invariant 3 is the point: adding a key to `config.yaml` binds nothing. The
check's job is to answer "does production read this key?", and the dangerous
answer is a false *yes* — a key waved through is a declaration nobody will ever
notice is inert. The first version of this check gave exactly that answer: it
searched for the bare word, and names like `ensembl` and `gnomad` occur in URLs
and module names, so the whole `api_rate_limits` block was excused while
nothing read it. That case is pinned here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".claude" / "hooks" / "_config_keys.py"


def _load():  # type: ignore[no-untyped-def]
    """Import `_config_keys` from the hooks directory."""
    spec = importlib.util.spec_from_file_location("_config_keys", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_config_keys"] = module
    spec.loader.exec_module(module)
    return module


ck = _load()


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a throwaway git repository containing `files`.

    A real repository, because the check uses `git grep` — a fake would test
    something other than what runs.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "f"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


class TestFlatten:
    """Every key, with parents marked."""

    def test_nested_keys_are_dotted_and_parents_flagged(self) -> None:
        """A parent is listed too, because a whole unread block must surface."""
        flat = ck.flatten_keys({"a": 1, "b": {"c": 2}})
        assert ("a", "a", False) in flat
        assert ("b", "b", True) in flat
        assert ("b.c", "c", False) in flat

    def test_an_empty_mapping_is_not_a_parent(self) -> None:
        """`b: {}` has no children to be read through."""
        flat = ck.flatten_keys({"b": {}})
        assert flat == [("b", "b", False)]

    def test_a_non_mapping_yields_nothing(self) -> None:
        """A list or scalar at the top is not a key space."""
        assert ck.flatten_keys([1, 2]) == []


class TestLookupPattern:
    """A key counts as read only in a lookup context, not as a loose word."""

    @pytest.mark.parametrize(
        "line",
        [
            'delay = config["ensembl"]',
            "delay = config.get('ensembl')",
            "delay = params.ensembl",
        ],
    )
    def test_lookup_forms_match(self, line: str) -> None:
        """Quoted key and attribute access are how config is actually read."""
        import re

        assert re.search(ck.lookup_pattern("ensembl"), line)

    @pytest.mark.parametrize(
        "line",
        [
            'URL = "https://rest.ensembl.org"',
            "# ensembl is rate limited",
            "from src.ensembl_client import fetch",
        ],
    )
    def test_loose_word_forms_do_not_match(self, line: str) -> None:
        """This is the false *yes* that excused `api_rate_limits`.

        If any of these matched, a key would count as wired because its name
        happens to appear in a URL, a comment or a module path.
        """
        import re

        assert not re.search(ck.lookup_pattern("ensembl"), line)


class TestUnwiredKeys:
    """End to end against a real git repository."""

    def test_a_key_nothing_reads_is_reported(self, tmp_path: Path) -> None:
        """The whole point: declared, never read."""
        root = _repo(tmp_path, {"src/m.py": "x = 1\n"})
        assert ck.unwired_keys({"orphan": 5}, root) == [
            ("orphan", "no production file reads it (searched src/, rules/, Snakefile)")
        ]

    def test_a_key_production_reads_is_not_reported(self, tmp_path: Path) -> None:
        """A real lookup clears the key."""
        root = _repo(tmp_path, {"src/m.py": 'v = config["threshold"]\n'})
        assert ck.unwired_keys({"threshold": 5}, root) == []

    def test_a_key_only_named_in_a_url_is_still_reported(
        self, tmp_path: Path
    ) -> None:
        """The regression that matters, as a whole-check test."""
        root = _repo(tmp_path, {"src/m.py": 'URL = "https://rest.ensembl.org"\n'})
        unwired = ck.unwired_keys({"ensembl": 15}, root)
        assert [name for name, _ in unwired] == ["ensembl"]

    def test_a_parent_is_excused_only_when_a_child_is_read(
        self, tmp_path: Path
    ) -> None:
        """"Read through its children" must not be an excuse on its own."""
        root = _repo(tmp_path, {"src/m.py": 'v = config["ncbi"]\n'})
        unwired = ck.unwired_keys({"limits": {"ncbi": 3}}, root)
        assert unwired == []

    def test_a_parent_with_no_read_children_is_reported_as_a_block(
        self, tmp_path: Path
    ) -> None:
        """An entirely unread block says so, rather than hiding behind its children."""
        root = _repo(tmp_path, {"src/m.py": "x = 1\n"})
        unwired = dict(ck.unwired_keys({"limits": {"ncbi": 3}}, root))
        assert "limits" in unwired
        assert "whole block unread" in unwired["limits"]

    def test_the_snakefile_counts_as_production(self, tmp_path: Path) -> None:
        """`results_dir` is read only there, and was reported until it counted."""
        root = _repo(tmp_path, {"Snakefile": 'D = config.get("results_dir", "results")\n'})
        assert ck.unwired_keys({"results_dir": "results"}, root) == []
