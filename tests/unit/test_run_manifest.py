"""Tests for run provenance (roadmap H10).

The manifest's value is entirely in what it refuses to claim. A record that
asserted "commit X produced this run" would be unfalsifiable and wrong for
every run written before the record existed, so the verdict logic is what
these tests pin hardest: a run whose outputs predate the commit must be
reported as impossible to attribute, and a dirty worktree must be reported as
undetermined rather than guessed either way.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core import manifest_writer
from src.core.run_manifest import (
    CANDIDATE,
    IMPOSSIBLE,
    SCHEMA_VERSION,
    UNDETERMINED,
    build_manifest,
    config_fingerprint,
    head_consistency,
    output_inventory,
    sha256_file,
    snakemake_state,
    stochastic_components,
)

ROOT = Path(__file__).resolve().parents[2]


class TestHashing:
    """Content hashes are the part that holds regardless of provenance."""

    def test_a_file_hashes_to_a_prefixed_digest(self, tmp_path: Path) -> None:
        """The algorithm travels with the digest."""
        target = tmp_path / "a.json"
        target.write_text("x", encoding="utf-8")
        digest = sha256_file(target)
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64

    def test_a_changed_byte_changes_the_digest(self, tmp_path: Path) -> None:
        """This is what makes a later hand-edit of a result detectable."""
        target = tmp_path / "a.json"
        target.write_text('{"score": 0.1}', encoding="utf-8")
        before = sha256_file(target)
        target.write_text('{"score": 0.2}', encoding="utf-8")
        assert sha256_file(target) != before


class TestHeadConsistency:
    """Whether the recorded commit could even be the producer."""

    def test_an_output_older_than_the_commit_rules_the_commit_out(self) -> None:
        """The decisive case: a run from September, a commit from today.

        Any record claiming this commit produced those numbers would be false,
        so the verdict has to be negative rather than optimistic.
        """
        code = {
            "head_committed_at": "2026-11-26T12:00:00+00:00",
            "worktree_clean": True,
        }
        verdict = head_consistency(code, [1_700_000_000.0])
        assert verdict["verdict"] == IMPOSSIBLE
        assert "earlier code" in verdict["reason"]

    def test_outputs_newer_than_a_clean_commit_make_it_a_candidate(self) -> None:
        """Even then it is a bound, and the wording says so."""
        code = {
            "head_committed_at": "2020-01-01T00:00:00+00:00",
            "worktree_clean": True,
        }
        verdict = head_consistency(code, [1_900_000_000.0])
        assert verdict["verdict"] == CANDIDATE
        assert "not proof" in verdict["reason"]

    def test_a_dirty_worktree_is_undetermined_not_a_candidate(self) -> None:
        """Uncommitted code is code no commit records."""
        code = {
            "head_committed_at": "2020-01-01T00:00:00+00:00",
            "worktree_clean": False,
        }
        verdict = head_consistency(code, [1_900_000_000.0])
        assert verdict["verdict"] == UNDETERMINED

    def test_unreadable_git_is_undetermined_not_a_candidate(self) -> None:
        """A manifest that cannot check must not claim (invariant 2)."""
        verdict = head_consistency({"head_committed_at": None}, [1.0])
        assert verdict["verdict"] == UNDETERMINED

    def test_no_outputs_is_undetermined(self) -> None:
        """An empty directory attests nothing."""
        code = {"head_committed_at": "2020-01-01T00:00:00+00:00", "worktree_clean": True}
        assert head_consistency(code, [])["verdict"] == UNDETERMINED


class TestInventory:
    """What gets hashed, and what must not be."""

    def test_the_manifest_excludes_itself(self, tmp_path: Path) -> None:
        """Hashing the manifest inside the manifest cannot converge."""
        (tmp_path / "stage1_tss.json").write_text("{}", encoding="utf-8")
        (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
        inventory, mtimes = output_inventory(tmp_path)
        assert set(inventory) == {"stage1_tss.json"}
        assert len(mtimes) == 1

    def test_every_entry_carries_hash_size_and_time(self, tmp_path: Path) -> None:
        """Size and time alone would not detect an equal-length edit."""
        (tmp_path / "stage7_scores.json").write_text('{"a": 1}', encoding="utf-8")
        inventory, _ = output_inventory(tmp_path)
        entry = inventory["stage7_scores.json"]
        assert set(entry) == {"sha256", "bytes", "modified_at"}
        assert entry["bytes"] == 8


class TestConfigFingerprint:
    """A missing config file is recorded as missing, never as a hash."""

    def test_a_missing_file_is_none(self, tmp_path: Path) -> None:
        """A fabricated digest for an absent file would be a false record."""
        prints = config_fingerprint(tmp_path)
        assert set(prints) == {
            "config/config.yaml",
            "config/cell_lines.yaml",
            "config/ccle_depmap_ids.yaml",
        }
        assert all(value is None for value in prints.values())

    def test_the_live_configs_hash(self) -> None:
        """The real repository's configs are all present and hashed."""
        prints = config_fingerprint(ROOT)
        assert all(
            value is not None and value.startswith("sha256:")
            for value in prints.values()
        )


class TestSnakemakeState:
    """An interrupted run has to say so."""

    def test_a_marker_for_this_run_is_reported(self, tmp_path: Path) -> None:
        """Markers are base64 of the output path, which is how we read them."""
        import base64

        run_dir = tmp_path / "results" / "GENE_LINE"
        run_dir.mkdir(parents=True)
        marker_dir = tmp_path / ".snakemake" / "incomplete"
        marker_dir.mkdir(parents=True)
        target = "results/GENE_LINE/stage2_seed_hits.json"
        (marker_dir / base64.b64encode(target.encode()).decode()).write_text("")
        state = snakemake_state(run_dir, tmp_path)
        assert state["incomplete_outputs"] == [target]

    def test_a_marker_for_another_run_is_not_reported(self, tmp_path: Path) -> None:
        """One run's interruption is not another run's problem."""
        import base64

        run_dir = tmp_path / "results" / "GENE_LINE"
        run_dir.mkdir(parents=True)
        marker_dir = tmp_path / ".snakemake" / "incomplete"
        marker_dir.mkdir(parents=True)
        other = "results/OTHER_LINE/stage2_seed_hits.json"
        (marker_dir / base64.b64encode(other.encode()).decode()).write_text("")
        assert snakemake_state(run_dir, tmp_path)["incomplete_outputs"] == []

    def test_a_same_named_run_elsewhere_on_disk_is_not_reported(
        self, tmp_path: Path
    ) -> None:
        """Directory names collide; full paths do not.

        An isolated run under a different `results_dir` has the same leaf name,
        and a marker it left was being reported against the repository's own
        run until this compared resolved paths.
        """
        import base64

        run_dir = tmp_path / "results" / "VEGFA_HeLa"
        run_dir.mkdir(parents=True)
        elsewhere = tmp_path / "scratch" / "results" / "VEGFA_HeLa"
        elsewhere.mkdir(parents=True)
        marker_dir = tmp_path / ".snakemake" / "incomplete"
        marker_dir.mkdir(parents=True)
        stray = str(elsewhere / "stage2_seed_hits.json")
        (marker_dir / base64.b64encode(stray.encode()).decode()).write_text("")
        assert snakemake_state(run_dir, tmp_path)["incomplete_outputs"] == []

    def test_the_manifests_own_marker_is_not_reported(self, tmp_path: Path) -> None:
        """Otherwise every manifest reports itself as unfinished.

        Snakemake writes the marker for an output while the job producing it
        runs, and the manifest is built inside that job — so it sees its own.
        """
        import base64

        run_dir = tmp_path / "results" / "GENE_LINE"
        run_dir.mkdir(parents=True)
        marker_dir = tmp_path / ".snakemake" / "incomplete"
        marker_dir.mkdir(parents=True)
        own = "results/GENE_LINE/manifest.json"
        (marker_dir / base64.b64encode(own.encode()).decode()).write_text("")
        assert snakemake_state(run_dir, tmp_path)["incomplete_outputs"] == []

    def test_an_undecodable_marker_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        """A stray file in the marker directory must not break a manifest."""
        run_dir = tmp_path / "results" / "GENE_LINE"
        run_dir.mkdir(parents=True)
        marker_dir = tmp_path / ".snakemake" / "incomplete"
        marker_dir.mkdir(parents=True)
        (marker_dir / "!!!not-base64!!!").write_text("")
        assert snakemake_state(run_dir, tmp_path)["incomplete_outputs"] == []


class TestStochasticComponents:
    """No seeds are recorded, and the reason is recorded instead."""

    def test_the_live_pipeline_reports_no_randomness_with_evidence(self) -> None:
        """`seeds: {}` would advertise bookkeeping that tracks nothing.

        If this ever fails, the pipeline gained a stochastic component and the
        manifest must start recording seeds — which is the point of asserting
        it rather than assuming it.
        """
        claim = stochastic_components(ROOT)
        assert claim["present"] is False
        assert claim["files"] == []
        assert "git grep" in claim["evidence"]


class TestBuildAndWrite:
    """The whole record, and the adapter that writes it."""

    def test_the_manifest_has_every_section(self, tmp_path: Path) -> None:
        """A section quietly going missing would shrink provenance in silence."""
        run_dir = tmp_path / "VEGFA_HeLa"
        run_dir.mkdir()
        (run_dir / "final_report.json").write_text("{}", encoding="utf-8")
        manifest = build_manifest(run_dir, ROOT)
        assert manifest["schema_version"] == SCHEMA_VERSION
        assert manifest["run"] == {
            "gene": "VEGFA",
            "cell_line": "HeLa",
            "dir": "VEGFA_HeLa",
        }
        for section in (
            "code",
            "head_consistency",
            "config",
            "external_data",
            "environment",
            "snakemake_state",
            "stochastic_components",
            "outputs",
        ):
            assert section in manifest, section

    def test_the_adapter_writes_valid_json(self, tmp_path: Path) -> None:
        """What lands on disk has to be readable by the next tool."""
        run_dir = tmp_path / "MYC_K562"
        run_dir.mkdir()
        (run_dir / "final_report.json").write_text("{}", encoding="utf-8")
        out = tmp_path / "manifest.json"
        manifest_writer.run(
            run_dir=str(run_dir),
            repo_root=str(ROOT),
            output_path=str(out),
            log_path=str(tmp_path / "m.log"),
        )
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["run"]["gene"] == "MYC"
        assert "final_report.json" in loaded["outputs"]
