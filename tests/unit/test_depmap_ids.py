"""Every DepMap ID in the config must name the cell line it is filed under.

Roadmap B18. Five of the seven non-null IDs named a different cell line
entirely: HeLa pointed at LC-1/sq-SF (lung), HepG2 at NCI-H1693 (lung), K562
at P3HR-1 (mature B-cell), Huh7 at Colo 794 (melanoma), GM12878 at HEL (AML).

The failure direction is what makes it serious. Both the wrong and the right
ACH IDs exist in `CCLE_Expression.csv`, so the lookup *succeeded* and returned
another cell line's real numbers — never an exception, never an unknown. A
confidently wrong value, which is worse than the unknown `B19` just installed,
because nothing anywhere logs a complaint.

Why it survived: the aggregate looked fine. Across 19,215 genes the configured
"HeLa" row and the real HeLa row correlate at r = 0.88, while 1,859 genes
differ by more than fourfold. And the biology checks in the reader's own tests
were *satisfied by the wrong line* — `test_k562_myc_high_expression` asserted
MYC at the 95th percentile with the comment "K562 is a leukemia line with very
high MYC", and P3HR-1 is a Burkitt lymphoma line whose MYC is translocated, so
it met that expectation better than K562 does (real K562 MYC sits at the 62nd
percentile). A plausible number from the wrong source is the hardest kind of
error to see.

The authority is DepMap's own `Model.csv`, vendored under `data/external/`
with its sha256 in the manifest so this check is offline and pinned. An ACH ID
is a stable identifier — DepMap does not reassign them — so a mismatch here is
a mapping error, never a release difference.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "ccle_depmap_ids.yaml"
MODELS = ROOT / "data" / "external" / "depmap" / "Model_24Q2.csv"
MANIFEST = ROOT / "data" / "external" / "manifest.json"

#: Cell lines with no DepMap model at all. `null` in the config is the honest
#: answer for these, and `B19` is what makes `null` safe: the lookup now
#: returns unknown rather than a risk-lowering zero.
NO_DEPMAP_MODEL = {"HEK293T", "GM12878"}


def _config() -> dict[str, str | None]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def _models() -> dict[str, dict[str, str]]:
    with MODELS.open(encoding="utf-8", newline="") as handle:
        return {row["ModelID"]: row for row in csv.DictReader(handle)}


@pytest.mark.skipif(not MODELS.is_file(), reason="DepMap Model.csv not vendored")
class TestEveryConfiguredIdNamesItsCellLine:
    def test_each_id_matches_its_config_key(self) -> None:
        models = _models()
        wrong: list[str] = []
        for name, ach in _config().items():
            if ach is None:
                continue
            row = models.get(ach)
            if row is None:
                wrong.append(f"{name}={ach} is not in Model.csv at all")
                continue
            stripped = (row.get("StrippedCellLineName") or "").upper()
            if stripped != name.upper():
                wrong.append(
                    f"{name}={ach} is actually "
                    f"{row.get('CellLineName')} ({row.get('OncotreePrimaryDisease')})"
                )
        assert not wrong, "DepMap IDs name the wrong cell line: " + "; ".join(wrong)

    def test_lines_without_a_depmap_model_are_null(self) -> None:
        """A line DepMap does not have must be `null`, not someone else's ID.

        GM12878 is absent from every field of `Model.csv`; it is a
        lymphoblastoid line, not a cancer line. Pointing it at `ACH-000004`
        (HEL, an AML line) produced real numbers for the wrong biology.
        """
        config = _config()
        for name in NO_DEPMAP_MODEL:
            assert name in config, f"{name} missing from the config entirely"
            assert config[name] is None, f"{name} should be null, is {config[name]!r}"

    def test_gm12878_really_is_absent_from_depmap(self) -> None:
        """Pinned so `null` stays justified rather than becoming folklore."""
        text = MODELS.read_text(encoding="utf-8")
        assert "GM12878" not in text

    def test_every_supported_cell_line_has_an_entry(self) -> None:
        """A cell line missing from the mapping silently loses its expression."""
        supported = yaml.safe_load(
            (ROOT / "config" / "cell_lines.yaml").read_text(encoding="utf-8")
        )
        names = set(supported.get("cell_lines", supported).keys())
        missing = names - set(_config())
        assert not missing, f"cell lines with no DepMap mapping decision: {missing}"


@pytest.mark.skipif(not MODELS.is_file(), reason="DepMap Model.csv not vendored")
class TestTheVendoredAuthorityIsPinned:
    """A vendored file with no recorded digest is a file nobody can re-verify."""

    def test_manifest_records_the_file_with_a_matching_sha256(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entries = [
            artifact
            for artifact in manifest.get("artifacts", [])
            if artifact.get("name") == MODELS.name
        ]
        assert entries, f"{MODELS.name} has no manifest entry"
        entry = entries[0]
        digest = hashlib.sha256(MODELS.read_bytes()).hexdigest()
        assert entry["sha256"] == digest, "manifest digest does not match the bytes"
        assert entry["bytes"] == MODELS.stat().st_size
        assert "B18" in entry.get("used_by", [])
