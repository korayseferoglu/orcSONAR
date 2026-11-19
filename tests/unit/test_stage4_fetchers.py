"""Failure direction of the Stage 4 `run()` adapters (roadmap B2a).

`B2` replaced the numeric fallback inside the reader modules with an explicit
unknown, but it never touched these four adapters, and they are the layer that
actually writes the JSON. Each one wraps the whole extraction in a `try` and,
on any exception, writes **0.0 for every site**:

    except Exception as exc:
        logger.warning(f"... — using 0.0")
        atac_signals = {sid: 0.0 for sid in site_ids}

For every one of these sources less signal reads as lower risk, so one failure
turns the entire channel into "nothing here" — the exact direction invariant 2
forbids and the one B2 was supposed to have closed.

B2 also handed them a way to trigger it: the readers now return `None` for an
unmeasured region, and `round(None, 4)` raises `TypeError`, which lands in
that same handler. A single unmeasured strand would therefore zero the channel
for *all* sites.

These adapters are part of the 0%-coverage layer (AUDIT.md Bulgu-3), which is
why neither problem was caught by a test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.stage4_epigenetic import (
    atac_fetcher,
    groseq_fetcher,
    hic_fetcher,
    histone_fetcher,
)

SITE = "VEGFA:ENST1:chr6:100"

#: adapter module, the class it builds, and the output keys it writes.
ADAPTERS = [
    (atac_fetcher, "ATACSeqReader", ["atac_signals"]),
    (groseq_fetcher, "GROseqReader", ["groseq_signals"]),
    (hic_fetcher, "HiCContactReader", ["hic_contacts"]),
    (histone_fetcher, "HistoneMarkReader", ["h3k4me3_signals", "h3k27ac_signals"]),
]


def _offtargets(tmp_path: Path) -> str:
    """A one-site stage-2 payload, written where the adapter expects it."""
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
    """Run one adapter and return the JSON it wrote."""
    out = tmp_path / "out.json"
    module.run(
        _offtargets(tmp_path),
        "HeLa",
        "config/cell_lines.yaml",
        str(out),
        str(tmp_path / "log.txt"),
    )
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("module", "reader", "keys"), ADAPTERS, ids=lambda v: getattr(v, "__name__", str(v)))
def test_a_failed_extraction_is_written_as_unknown(
    module: Any, reader: str, keys: list[str], tmp_path: Path
) -> None:
    """A dead source must not write a number that reads as "no signal"."""
    with patch.object(module, reader, side_effect=RuntimeError("source down")):
        payload = _run(module, tmp_path)
    for key in keys:
        assert payload[key][SITE] is None, (
            f"{module.__name__}: {key} wrote {payload[key][SITE]!r} for a failed "
            "source; less signal reads as lower risk, so this makes the site "
            "look safe (invariant 2)"
        )
