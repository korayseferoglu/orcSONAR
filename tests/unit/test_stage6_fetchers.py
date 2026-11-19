"""Failure direction of the Stage 6 `run()` adapters (audit Bulgu 3).

`B2a` found and fixed this exact pattern in the four Stage 4 adapters. The
search stopped there, so the Stage 6 producers kept writing numbers on
failure — and `execution_merger`'s own docstring describes why that is the
worst place for it:

    Contributing a zero instead would lower the risk on the strength of data
    nobody has, and for Ago2 — the heaviest channel at 0.40 — that single
    substitution moved a site most of the way to "safe".

`ago2_fetcher` did exactly that: `"loading_score": 0.0, "is_loaded": False`.
So the merger waited for a sentinel its own producer never sent, and B2's
renormalisation branch was unreachable through the failure path it was
written for.

`is_loaded`/`is_competing` were `False` for the same reason, although B2's
roadmap entry says plainly that those must be `bool | None`, because writing
`False` asserts "not loaded" — a claim, and in the safe direction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.stage6_execution import ago2_fetcher, circrna_checker, rbp_fetcher

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
                            "chrom": "chr6",
                            "start": 100,
                            "end": 120,
                            "strand": "+",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def _run(module: Any, tmp_path: Path) -> dict[str, Any]:
    out = tmp_path / "out.json"
    module.run(
        _offtargets(tmp_path),
        "HeLa",
        "config/cell_lines.yaml",
        str(out),
        str(tmp_path / "log.txt"),
    )
    return json.loads(out.read_text(encoding="utf-8"))


#: adapter, the symbol to break, the results key, and the fields that must be
#: unknown rather than a confident number.
ADAPTERS = [
    (ago2_fetcher, "assess_ago2_loading", "ago2_results", ("raw_signal", "loading_score", "is_loaded")),
    (rbp_fetcher, "assess_rbp_competition", "rbp_results", ("raw_signal", "competition_score", "is_competing")),
]


@pytest.mark.parametrize(
    ("module", "symbol", "key", "fields"), ADAPTERS, ids=lambda v: getattr(v, "__name__", str(v))
)
def test_a_failed_source_is_written_as_unknown(
    module: Any, symbol: str, key: str, fields: tuple[str, ...], tmp_path: Path
) -> None:
    with patch.object(module, symbol, side_effect=RuntimeError("source down")):
        payload = _run(module, tmp_path)
    record = payload[key][SITE]
    for field in fields:
        assert record[field] is None, (
            f"{module.__name__}: {field} wrote {record[field]!r} for a failed "
            "source. For Ago2 this is the 0.40-weight channel the merger's own "
            "docstring warns about (invariant 2)."
        )


def test_circrna_failure_is_unknown_not_absence_of_a_sponge(tmp_path: Path) -> None:
    """`sponge_risk: False` claims no circRNA overlaps; a dead source knows nothing."""
    with patch.object(circrna_checker, "check_circrna_overlap", side_effect=RuntimeError("down")):
        out = tmp_path / "out.json"
        circrna_checker.run(
            _offtargets(tmp_path),
            "data/5_Icra_Güvenlik/circAtlas",
            str(out),
            str(tmp_path / "log.txt"),
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
    record = payload["circrna_results"][SITE]
    assert record["sponge_risk"] is None
    assert record["overlap_count"] is None
