"""Tests for the single-copy gate's logic (roadmap H9).

The gate's whole value is in what it does *not* flag. A content gate that
cries wolf gets switched off on day one — H9's own roadmap row says so, and
`H15`'s row records that exact failure already happening in this repo: its
first version flagged comments *describing* the pattern it was hunting.

So these tests pin the four distinctions the design rests on, each with a case
that must stay green, and one case that must go red:

* stating a fact (red) vs. pointing at its authority (green)
* a fact's current value (red) vs. a dated record of what it used to be (green)
* prose restating a fact (red) vs. code using it (green)
* a known-open duplicate with a roadmap item (green) vs. a new one (red)

The red case is the one that makes the rest meaningful: `test_a_new_duplicate_
is_caught` is the proof that a green run means something.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".claude" / "hooks" / "_single_copy.py"


def _load():  # type: ignore[no-untyped-def]
    """Import `_single_copy` from its hooks directory.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location("_single_copy", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_single_copy"] = module
    spec.loader.exec_module(module)
    return module


sc = _load()


def _registry(**overrides: object) -> dict[str, object]:
    """Build a one-fact registry for the tests.

    Args:
        **overrides: Fields to override on the single fact.

    Returns:
        A parsed-YAML-shaped mapping.
    """
    fact: dict[str, object] = {
        "id": "seed_slice",
        "gercek": "seed dilimi",
        "otorite": ".claude/rules/10-koordinatlar.md",
        "patterns": [r"\[1:8\]"],
        "pointer_tokens": ["10-koordinatlar"],
    }
    fact.update(overrides)
    return {"facts": [fact]}


def _one_fact(**overrides: object):  # type: ignore[no-untyped-def]
    """Load the single fact from `_registry`.

    Args:
        **overrides: Fields to override.

    Returns:
        The parsed `Fact`.
    """
    return sc.load_registry(_registry(**overrides))[0]


class TestWhatCountsAsStatingAFact:
    """The line-level decision, which is where false positives come from."""

    def test_a_new_duplicate_is_caught(self, tmp_path: Path) -> None:
        """A plain restatement in a non-authority file is a violation.

        This is the gate's reason to exist: without this case passing, every
        other test here only proves the gate is quiet.
        """
        (tmp_path / "notes.md").write_text(
            "The seed is `[1:8]` of the guide.\n", encoding="utf-8"
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["notes.md"])
        assert len(violations) == 1
        assert violations[0].fact_id == "seed_slice"
        assert violations[0].line == 1

    def test_the_authority_may_state_its_own_fact(self, tmp_path: Path) -> None:
        """The authority file is never a second copy."""
        rel = ".claude/rules/10-koordinatlar.md"
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text("Seed `[1:8]`.\n", encoding="utf-8")
        violations, skipped = sc.scan(tmp_path, [_one_fact()], [rel])
        assert violations == []
        assert skipped == {"authority": 1}

    def test_a_line_pointing_at_the_authority_is_fine(self, tmp_path: Path) -> None:
        """Naming a fact in order to send the reader elsewhere is the goal."""
        (tmp_path / "notes.md").write_text(
            "Seed slice `[1:8]`: see `.claude/rules/10-koordinatlar.md`.\n",
            encoding="utf-8",
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["notes.md"])
        assert violations == []

    def test_a_disclaimer_on_a_neighbouring_line_is_fine(
        self, tmp_path: Path
    ) -> None:
        """A refusal to own the fact can sit on the next line.

        `10-koordinatlar.md` names two formats' coordinate bases on one line
        and declines to own them on the next. Judging the line alone reads it
        as the very duplication it is refusing to make.
        """
        (tmp_path / "notes.md").write_text(
            "Örnek: seed `[1:8]`.\nBuraya kopyalamıyorum, tablo burada değil.\n",
            encoding="utf-8",
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["notes.md"])
        assert violations == []

    def test_a_dated_record_of_the_old_value_is_fine(self, tmp_path: Path) -> None:
        """Past-tense history creates no drift risk about the current value."""
        (tmp_path / "notes.md").write_text(
            "The seed used to be `[1:8]` before the change.\n", encoding="utf-8"
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["notes.md"])
        assert violations == []

    def test_a_co_pattern_must_also_match(self, tmp_path: Path) -> None:
        """`co_patterns` separates the fact from a parameter's own contract.

        "region: Genomic interval (chr-prefixed, hg38)" documents an argument;
        "4DN contigs carry no chr prefix" states the canonical fact. Only the
        second names a source.
        """
        fact = _one_fact(
            patterns=[r"chr[ -]?prefix"], co_patterns=[r"\b(?:4DN|ENCODE)\b"]
        )
        (tmp_path / "a.md").write_text(
            "region: interval (chr-prefixed, hg38).\n", encoding="utf-8"
        )
        (tmp_path / "b.md").write_text(
            "4DN contigs carry no chr-prefix.\n", encoding="utf-8"
        )
        violations, _ = sc.scan(tmp_path, [fact], ["a.md", "b.md"])
        assert [v.path for v in violations] == ["b.md"]


class TestProseVersusCode:
    """Only prose is scanned: a slice is the fact being used, not restated."""

    def test_an_expression_using_the_value_is_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """`seed = guide[1:8]` is the consumer, not a second authority."""
        (tmp_path / "m.py").write_text("seed = guide[1:8]\n", encoding="utf-8")
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["m.py"])
        assert violations == []

    def test_a_comment_restating_the_value_is_flagged(self, tmp_path: Path) -> None:
        """The same value in a comment is a copy that can drift."""
        (tmp_path / "m.py").write_text(
            "# Seed region is `[1:8]` of the guide.\nseed = guide[1:8]\n",
            encoding="utf-8",
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["m.py"])
        assert [v.line for v in violations] == [1]

    def test_a_docstring_restating_the_value_is_flagged(
        self, tmp_path: Path
    ) -> None:
        """Docstrings are prose too."""
        (tmp_path / "m.py").write_text(
            '"""Extract the seed, `[1:8]` of the guide."""\n', encoding="utf-8"
        )
        violations, _ = sc.scan(tmp_path, [_one_fact()], ["m.py"])
        assert [v.line for v in violations] == [1]

    def test_unparsable_python_still_yields_its_comments(
        self, tmp_path: Path
    ) -> None:
        """A syntax error must not silently empty the scan.

        Failing open here would mean a file could dodge the gate by not
        compiling, which is the wrong failure direction (invariant 2).
        """
        (tmp_path / "broken.py").write_text(
            "# seed `[1:8]`\ndef f(:\n", encoding="utf-8"
        )
        lines = sc.prose_lines(tmp_path / "broken.py", (tmp_path / "broken.py").read_text())
        assert any("[1:8]" in text for _, text in lines)


class TestCarveOuts:
    """Known-open debt stays visible and keeps pointing somewhere."""

    def test_a_carve_out_suppresses_its_path(self, tmp_path: Path) -> None:
        """A documented duplicate does not fail the gate."""
        (tmp_path / "README.md").write_text("Seed `[1:8]`.\n", encoding="utf-8")
        fact = _one_fact(
            carve_outs=[{"path": "README.md", "roadmap": "H9c", "reason": "x"}]
        )
        violations, skipped = sc.scan(tmp_path, [fact], ["README.md"])
        assert violations == []
        assert skipped == {"carve-out → H9c": 1}

    def test_a_carve_out_without_a_roadmap_item_is_rejected(self) -> None:
        """An exemption nobody will ever remove is a deletion in disguise."""
        with pytest.raises(ValueError, match="roadmap"):
            sc.load_registry(
                _registry(carve_outs=[{"path": "README.md", "roadmap": ""}])
            )

    def test_a_fact_without_patterns_needs_a_stated_reason(self) -> None:
        """Silent non-coverage is the exit-0 trap the acceptance README warns of."""
        with pytest.raises(ValueError, match="unmeasured_reason"):
            sc.load_registry(_registry(patterns=[]))

    def test_a_fact_missing_its_authority_is_rejected(self) -> None:
        """A fact with no authority cannot classify anything."""
        with pytest.raises(ValueError, match="otorite"):
            sc.load_registry(_registry(otorite=""))


class TestTableAndRegistryAgree:
    """The registry and the prose table are two renderings of one fact."""

    def test_ids_are_read_from_the_table(self) -> None:
        """The id column of the real authority table parses."""
        markdown = (ROOT / ".claude" / "rules" / "00-degismezler.md").read_text(
            encoding="utf-8"
        )
        ids = sc.authority_table_ids(markdown)
        assert "fallback_sentineli" in ids
        assert "is_sirasi" in ids

    def test_a_row_added_to_only_one_side_is_caught(self) -> None:
        """Adding to the table without the registry must not pass silently."""
        markdown = (
            "## Kanonik gerçekler nerede yazılı\n\n"
            "| id | gerçek | otorite |\n|---|---|---|\n"
            "| `seed_slice` | seed | `a.md` |\n"
            "| `yeni_gercek` | yeni | `b.md` |\n"
        )
        ids = sc.authority_table_ids(markdown)
        registry_ids = [f.id for f in sc.load_registry(_registry())]
        assert sorted(set(ids) ^ set(registry_ids)) == ["yeni_gercek"]
