"""Shared pytest fixtures for orcSONAR test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import GenomicRegion, SarnaInput


@pytest.fixture
def sample_region() -> GenomicRegion:
    """A canonical VEGFA promoter-proximal region on chr6."""
    return GenomicRegion(chrom="chr6", start=43768652, end=43769652, strand="+")


@pytest.fixture
def sample_sarna_input() -> SarnaInput:
    """Default proof-of-concept saRNA targeting VEGFA in HeLa."""
    return SarnaInput(
        sequence="GCAACCATAGCCTCGGCCGC",
        target_gene="VEGFA",
        cell_line="HeLa",
    )


@pytest.fixture
def tmp_cache_db(tmp_path: Path) -> Path:
    """Temporary SQLite cache database path."""
    return tmp_path / "test_cache.db"


@pytest.fixture
def tmp_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml to a temp file."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "target_gene: VEGFA\n"
        "cell_line: HeLa\n"
        "sarna_sequence: GCAACCATAGCCTCGGCCGC\n",
        encoding="utf-8",
    )
    return cfg
