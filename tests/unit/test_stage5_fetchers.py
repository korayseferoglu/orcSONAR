"""Failure direction of the Stage 5 `run()` adapters (audit Bulgu 2).

`B2a` fixed this pattern in Stage 4 and `R2.1` in Stage 6. Stage 5 kept it:
each adapter answers a dead source with a number, and for every one of these
channels a smaller number is a lower risk, so one failure makes the site look
clean. `biophysics_merger` weights them at 0.25 (SHAPE), 0.15 (m6A), 0.15
(ADAR) and 0.10 (G4).

SHAPE is the one that matters most here: `accessibility_score = 0.5` was
written both when the icSHAPE file was missing *and* when it was read, so the
run could not tell the two apart — and `circatlas_shape_data` memory records
that only 6 of 41 sites ever carried real signal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.stage5_biophysics import adar_estimator, g4_detector, m6a_mapper, shape_reader

SITE = "VEGFA:ENST1:chr6:100"


def _offtargets(tmp_path: Path) -> str:
    path = tmp_path / "offtargets.json"
    path.write_text(
        json.dumps(
            {
                "offtarget_sites": [
                    {
                        "site_id": SITE,
                        "gene": "VEGFA",
                        "transcript_id": "ENST1",
                        "region": {
                            "chrom": "chr6", "start": 100, "end": 120, "strand": "+",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return str(path)


#: adapter, symbol to break, results key, call args, fields that must be unknown.
CASES = [
    (
        shape_reader, "get_shape_accessibility", "shape_results",
        lambda p, out, log: (p, "data/4_Biyofizik_Yapısal/SHAPE_Seq", "HeLa", out, log),
        ("mean_reactivity", "accessibility_score", "single_stranded_fraction"),
    ),
    (
        adar_estimator, "calculate_adar_risk", "adar_results",
        lambda p, out, log: (p, "https://api.genome.ucsc.edu", out, log),
        ("alu_risk", "shape_ds_risk", "adar_score"),
    ),
    (
        m6a_mapper, "scan_m6a_sites", "m6a_results",
        lambda p, out, log: (p, "data/4_Biyofizik_Yapısal/RMBase/x.bed.gz", "HeLa", out, log),
        ("site_count", "m6a_score"),
    ),
]


@pytest.mark.parametrize(
    ("module", "symbol", "key", "args", "fields"),
    CASES,
    ids=lambda v: getattr(v, "__name__", ""),
)
def test_a_failed_source_is_written_as_unknown(
    module: Any, symbol: str, key: str, args: Any, fields: tuple[str, ...], tmp_path: Path
) -> None:
    out = tmp_path / "out.json"
    log = str(tmp_path / "log.txt")
    with patch.object(module, symbol, side_effect=RuntimeError("source down")):
        module.run(*args(_offtargets(tmp_path), str(out), log))
    record = json.loads(out.read_text(encoding="utf-8"))[key][SITE]
    for field in fields:
        assert record[field] is None, (
            f"{module.__name__}: {field} wrote {record[field]!r} for a failed "
            "source; on these channels a smaller number is a lower risk "
            "(invariant 2)"
        )


def test_g4_detection_failure_is_unknown(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    with patch.object(g4_detector, "detect_g4", side_effect=RuntimeError("down")):
        g4_detector.run(_offtargets(tmp_path), str(out), str(tmp_path / "log.txt"))
    record = json.loads(out.read_text(encoding="utf-8"))["g4_results"][SITE]
    assert record["risk_score"] is None
    assert record["g4_count"] is None
