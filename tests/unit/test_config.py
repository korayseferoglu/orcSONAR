"""Unit tests for src/core/config.py."""

import pytest
from pydantic import ValidationError

from src.core.config import ScoringWeights, load_config


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
