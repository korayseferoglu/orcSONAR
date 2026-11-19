"""Unit tests for src/core/config.py."""

import pytest
from pydantic import ValidationError

from src.core.config import ScoringWeights, config_from_mapping, load_config


class TestScoringWeights:
    def test_defaults_sum_to_one(self):
        w = ScoringWeights()
        total = (
            w.sequence_specificity
            + w.variant_toxicity
            + w.biophysics_structure
            + w.epigenetic_context
            + w.execution_safety
        )
        assert abs(total - 1.0) < 1e-6

    def test_invalid_sum_raises(self):
        # Narrowed from `pytest.raises(Exception)` (roadmap H15). A blind assert
        # passes on any failure — measured: with a typo'd field name the old
        # version still passed while the validator under test never ran.
        with pytest.raises(ValidationError, match="scoring_weights"):
            ScoringWeights(
                sequence_specificity=0.5,
                variant_toxicity=0.5,
                biophysics_structure=0.5,
                epigenetic_context=0.5,
                execution_safety=0.5,
            )


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_config_yaml):
        cfg = load_config(tmp_config_yaml)
        assert cfg.target_gene == "VEGFA"
        assert cfg.cell_line == "HeLa"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_cell_line_raises(self, tmp_path):
        bad_cfg = tmp_path / "bad.yaml"
        bad_cfg.write_text("cell_line: InvalidCell\n", encoding="utf-8")
        # Typed AND matched: this must fail because the cell line is unknown,
        # not because the stub config is missing other required fields (H15).
        with pytest.raises(ValidationError, match="cell_line"):
            load_config(bad_cfg)

    def test_default_values(self, tmp_config_yaml):
        cfg = load_config(tmp_config_yaml)
        assert cfg.promoter_upstream == 1000
        assert cfg.promoter_downstream == 200
        assert cfg.seed_length == 7
        assert cfg.max_mismatches == 3

    def test_scoring_weights_present(self, tmp_config_yaml):
        cfg = load_config(tmp_config_yaml)
        assert cfg.scoring_weights.sequence_specificity == pytest.approx(0.20)


class TestConfigFromMapping:
    """Snakemake's merged config must reach the adapters.

    Audit 2026-11-19, Bulgu 13: ``load_config`` had exactly one production
    caller, so fourteen adapters built ``OrcSonarConfig(...)`` from their
    rule's params and every unpassed field fell back to a hardcoded default.
    ``cache_db`` is read in fourteen places across ten modules and was passed
    by no rule, which is why a configured cache path was ignored.
    """

    def test_data_paths_survive_the_hand_off(self) -> None:
        cfg = config_from_mapping(
            {"data_paths": {"cache_db": "/tmp/elsewhere/cache.db"}}
        )
        assert cfg.data_paths.cache_db == "/tmp/elsewhere/cache.db"

    def test_defaults_apply_when_nothing_is_passed(self) -> None:
        cfg = config_from_mapping(None)
        assert cfg.data_paths.cache_db == "data/cache/orcsonar_cache.db"

    def test_overrides_win_over_the_mapping(self) -> None:
        """A rule's own params beat the file, as --config does in Snakemake."""
        cfg = config_from_mapping({"target_gene": "VEGFA"}, target_gene="MYC")
        assert cfg.target_gene == "MYC"

    def test_the_mapping_is_not_mutated(self) -> None:
        """Snakemake's config dict is shared across rules; it must not be edited."""
        raw = {"target_gene": "VEGFA"}
        config_from_mapping(raw, target_gene="MYC")
        assert raw == {"target_gene": "VEGFA"}


class TestAdaptersReceiveTheConfiguredPaths:
    """Every rule must hand its adapter the merged config.

    Bulgu 13's harm was concrete and measured: ``cache_db`` is read in
    fourteen places across ten modules and no rule passed it, so a configured
    cache path was ignored and the audit's own isolation failed — one module
    honoured the scratch copy while another opened the live database.
    """

    _ADAPTERS = (
        "transcript_resolver", "tss_mapper", "repeat_scanner", "seed_aligner",
        "clinvar_client", "gnomad_client", "atac_fetcher", "ccle_reader",
        "groseq_fetcher", "hic_fetcher", "histone_fetcher", "g4_detector",
        "ago2_fetcher", "rbp_fetcher",
    )

    def test_every_adapter_run_accepts_config_raw(self) -> None:
        import importlib
        import inspect

        missing: list[str] = []
        for name in self._ADAPTERS:
            module = next(
                importlib.import_module(f"src.{pkg}.{name}")
                for pkg in (
                    "stage1_genomic_map", "stage2_offtarget_scan", "stage3_variant_tox",
                    "stage4_epigenetic", "stage5_biophysics", "stage6_execution",
                )
                if importlib.util.find_spec(f"src.{pkg}.{name}") is not None
            )
            if "config_raw" not in inspect.signature(module.run).parameters:
                missing.append(name)
        assert not missing, f"these run() adapters cannot receive the config: {missing}"

    def test_every_rule_passes_config_to_its_adapter(self) -> None:
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        call = re.compile(
            r"\b(" + "|".join(self._ADAPTERS) + r")\.run\(\n((?:.*\n)*?)\s*\)\n"
        )
        offenders: list[str] = []
        for smk in sorted((root / "rules").glob("*.smk")):
            for match in call.finditer(smk.read_text(encoding="utf-8")):
                if "config_raw=config" not in match.group(2):
                    offenders.append(f"{smk.name}: {match.group(1)}.run()")
        assert not offenders, (
            "these rules build their adapter's config from params alone, so "
            "every unpassed field silently falls back to a hardcoded default:\n  "
            + "\n  ".join(offenders)
        )


class TestNoModuleHardcodesTheCachePath:
    """The guard must not inherit the blind spot of the fix it guards.

    R0.3 found its fourteen adapters by grepping for ``OrcSonarConfig(``, and
    the test written with it listed those same fourteen. Both missed
    ``phylop_scorer``, which took ``cache_db`` as a *default parameter*
    holding the literal live path, and ``ccle_reader``, which passed a
    ``data_paths`` override that replaced the whole section and reverted
    ``cache_db`` to its default.

    Neither showed up in any test. They showed up in a real run: the
    per-rule logs recorded seven opens of ``data/cache/orcsonar_cache.db``
    while the other forty-seven used the configured path (audit 2026-11-19).

    So this test checks a *property* instead of a list — nothing outside
    core/config.py may spell the cache path.
    """

    def test_the_literal_cache_path_appears_only_in_core_config(self) -> None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        needle = "data/cache/orcsonar_cache.db"
        offenders: list[str] = []
        for path in sorted((root / "src").rglob("*.py")):
            if path.name == "config.py":
                continue  # the one legitimate home of the default
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if needle in line:
                    offenders.append(f"{path.relative_to(root)}:{lineno}")
        assert not offenders, (
            "these spell the cache path instead of reading it from config, so "
            "a configured path does not reach them:\n  " + "\n  ".join(offenders)
        )

    def test_a_nested_override_does_not_wipe_its_siblings(self) -> None:
        """The bug that sent ccle_reader to the live cache."""
        cfg = config_from_mapping(
            {"data_paths": {"cache_db": "/tmp/mine.db", "ccle_csv": "/tmp/old.csv"}},
            data_paths={"ccle_csv": "/tmp/new.csv"},
        )
        assert cfg.data_paths.ccle_csv == "/tmp/new.csv"
        assert cfg.data_paths.cache_db == "/tmp/mine.db", (
            "a data_paths override replaced the whole section and cache_db "
            "fell back to its default"
        )
