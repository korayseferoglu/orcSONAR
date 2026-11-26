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


class TestVerifiedCopies:
    """A number may be repeated only where the gate recomputes it.

    The rule's reason is that copies drift; this repo's scar is two docstrings
    still reading "~250 genes" for a set of 183. A copy checked against the
    authority on every run cannot drift silently, so it keeps the information a
    README reader wants without keeping the risk.
    """

    def _fact(self, tmp_path: Path, pattern: str = r"(\d+)-gene background"):  # type: ignore[no-untyped-def]
        """A fact whose README copy is value-checked against the gene count."""
        return sc.load_registry(
            _registry(
                id="background",
                gercek="arama uzayı boyutu",
                otorite="src/x.py",
                patterns=[r"(\d+)-gene background"],
                verified_copies=[
                    {
                        "path": "README.md",
                        "pattern": pattern,
                        "value_source": "background_gene_count",
                    }
                ],
            )
        )[0]

    def _repo(self, tmp_path: Path, readme: str, genes: int) -> Path:
        """Build a tiny repo whose authority defines `genes` entries."""
        (tmp_path / "README.md").write_text(readme, encoding="utf-8")
        src = tmp_path / "src" / "stage2_offtarget_scan"
        src.mkdir(parents=True)
        names = ", ".join(f'"G{i}"' for i in range(genes))
        (src / "transcriptome_fetcher.py").write_text(
            f"_BACKGROUND_GENES = ({names},)\n", encoding="utf-8"
        )
        return tmp_path

    def test_a_matching_copy_is_allowed_and_not_a_violation(
        self, tmp_path: Path
    ) -> None:
        """The stated number equals the authority, so the line is fine."""
        root = self._repo(tmp_path, "a 3-gene background set\n", 3)
        fact = self._fact(tmp_path)
        violations, _ = sc.scan(root, [fact], ["README.md"])
        problems, checked = sc.check_verified_copies(root, [fact])
        assert violations == []
        assert problems == []
        assert checked == 1

    def test_a_drifted_copy_is_caught(self, tmp_path: Path) -> None:
        """The number went stale against the authority — the drift case."""
        root = self._repo(tmp_path, "a 3-gene background set\n", 5)
        problems, _ = sc.check_verified_copies(root, [self._fact(tmp_path)])
        assert len(problems) == 1
        assert "(3,)" in problems[0] and "(5,)" in problems[0]

    def test_a_declaration_that_matches_nothing_is_caught(
        self, tmp_path: Path
    ) -> None:
        """A stale declaration guards nothing and must not pass quietly.

        If the document stops stating the fact, the entry becomes an exemption
        over empty space, and the next real duplicate in that file slips by.
        """
        root = self._repo(tmp_path, "no number here\n", 3)
        problems, checked = sc.check_verified_copies(root, [self._fact(tmp_path)])
        assert checked == 0
        assert len(problems) == 1
        assert "BAYAT" in problems[0]

    def test_every_line_the_pattern_covers_is_value_checked(
        self, tmp_path: Path
    ) -> None:
        """A second copy in the same file is checked too, not excused by the first.

        The declaration exempts a line from the *duplication* finding only
        because the same line is then compared against the authority. So a
        second, disagreeing number in that file surfaces as a value problem
        rather than slipping through.
        """
        root = self._repo(
            tmp_path,
            "a 3-gene background set\nand elsewhere a 9-gene background claim\n",
            3,
        )
        fact = self._fact(tmp_path)
        violations, _ = sc.scan(root, [fact], ["README.md"])
        problems, checked = sc.check_verified_copies(root, [fact])
        assert violations == []
        assert checked == 2
        assert len(problems) == 1
        assert "README.md:2" in problems[0]

    def test_a_phrasing_the_declaration_does_not_cover_stays_a_violation(
        self, tmp_path: Path
    ) -> None:
        """The excuse is per line AND per pattern, never per file.

        A file-level exemption would also cover statements of the same fact in
        forms nobody is checking — which is how an exemption becomes a hole.
        """
        fact = sc.load_registry(
            _registry(
                id="background",
                gercek="arama uzayı boyutu",
                otorite="src/x.py",
                patterns=[r"(\d+)-gene background", r"background set of \d+"],
                verified_copies=[
                    {
                        "path": "README.md",
                        "pattern": r"(\d+)-gene background",
                        "value_source": "background_gene_count",
                    }
                ],
            )
        )[0]
        root = self._repo(
            tmp_path, "a 3-gene background set\nbackground set of 3\n", 3
        )
        violations, _ = sc.scan(root, [fact], ["README.md"])
        assert [v.line for v in violations] == [2]

    def test_a_copy_without_a_capture_group_is_rejected(self) -> None:
        """Nothing to compare means nothing is verified."""
        with pytest.raises(ValueError, match="capture group"):
            sc.load_registry(
                _registry(
                    verified_copies=[
                        {
                            "path": "README.md",
                            "pattern": "no groups here",
                            "value_source": "background_gene_count",
                        }
                    ]
                )
            )

    def test_an_unknown_value_source_is_rejected(self) -> None:
        """A resolver that does not exist cannot check anything."""
        with pytest.raises(ValueError, match="value_source"):
            sc.load_registry(
                _registry(
                    verified_copies=[
                        {
                            "path": "README.md",
                            "pattern": r"(\d+)",
                            "value_source": "nope",
                        }
                    ]
                )
            )


class TestCarveOutsStopMeaningSomething:
    """An exemption has to keep pointing at work that will remove it."""

    def _facts(self, roadmap: str):  # type: ignore[no-untyped-def]
        """One fact carrying a single carve-out aimed at `roadmap`."""
        return sc.load_registry(
            _registry(
                carve_outs=[
                    {"path": "README.md", "roadmap": roadmap, "reason": "x"}
                ]
            )
        )

    @staticmethod
    def _is_done(status: str) -> bool:
        """Minimal stand-in for `_status.is_done`."""
        return "DONE" in status

    def test_an_open_item_is_fine(self) -> None:
        """The normal case: the debt is recorded and still owed."""
        assert sc.stale_carve_outs(self._facts("H9c"), {"h9c": "TODO"}, self._is_done) == []

    def test_an_item_the_roadmap_never_defines_is_caught(self) -> None:
        """Nobody will ever close `H99`, so this exemption is permanent."""
        problems = sc.stale_carve_outs(self._facts("H99"), {"h9c": "TODO"}, self._is_done)
        assert len(problems) == 1
        assert "böyle bir" in problems[0]

    def test_a_carve_out_outliving_its_item_is_caught(self) -> None:
        """Once the item closed, the duplicate should have gone with it.

        This is the quiet rot the gate is for: the item is ticked, everyone
        believes the copy is gone, and the exemption keeps covering it.
        """
        problems = sc.stale_carve_outs(
            self._facts("B8"), {"b8": "**DONE**"}, self._is_done
        )
        assert len(problems) == 1
        assert "KAPANDI" in problems[0]


class TestResolvers:
    """Authority values are read without importing anything.

    `ast` and YAML rather than an import, because the gate runs in CI where
    `data/` is absent: a module that touched a data file at import time would
    make the gate's own verdict depend on data availability.
    """

    def test_a_module_level_tuple_is_counted(self, tmp_path: Path) -> None:
        """The gene count comes from the literal, not from running the module."""
        src = tmp_path / "src" / "stage2_offtarget_scan"
        src.mkdir(parents=True)
        (src / "transcriptome_fetcher.py").write_text(
            '_BACKGROUND_GENES = ("A", "B")\nimport nonexistent_module_xyz\n',
            encoding="utf-8",
        )
        assert sc.resolve_value("background_gene_count", tmp_path) == (2,)

    def test_a_missing_name_is_an_error_not_a_zero(self, tmp_path: Path) -> None:
        """Returning 0 would make every stated count look wrong for the wrong reason."""
        src = tmp_path / "src" / "stage2_offtarget_scan"
        src.mkdir(parents=True)
        (src / "transcriptome_fetcher.py").write_text("X = 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="_BACKGROUND_GENES"):
            sc.resolve_value("background_gene_count", tmp_path)

    def test_the_live_repository_resolves(self) -> None:
        """The real authorities answer, which is what CI depends on."""
        assert sc.resolve_value("background_gene_count", ROOT) == (183,)
        assert sc.resolve_value("promoter_window", ROOT) == (1000, 200)
        assert sc.resolve_value("seed_positions", ROOT) == (2, 8)


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
