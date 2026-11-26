"""Snakemake run() adapter for the run manifest (roadmap H10)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

from src.core.run_manifest import CANDIDATE, IMPOSSIBLE, build_manifest


def run(run_dir: str, repo_root: str, output_path: str, log_path: str) -> None:
    """Write ``manifest.json`` describing how a run directory came to be.

    Args:
        run_dir: Directory holding one run's outputs.
        repo_root: Repository root, used for git and config lookups.
        output_path: Destination manifest path.
        log_path: Log file path.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    manifest = build_manifest(Path(run_dir), Path(repo_root))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    verdict = manifest["head_consistency"]["verdict"]
    count = len(manifest["outputs"])
    logger.info(f"manifest_writer: {count} output(s) hashed → {output_path}")
    if verdict == CANDIDATE:
        logger.info("manifest_writer: HEAD is a candidate producer of this run")
    elif verdict == IMPOSSIBLE:
        # Not a warning about the manifest — the manifest is correct. It is a
        # warning about the RUN: these numbers were produced by code that is no
        # longer what HEAD says, which is exactly what roadmap B12 re-runs.
        logger.warning(
            "manifest_writer: HEAD CANNOT have produced this run — the outputs "
            "predate the recorded commit (roadmap B12)"
        )
    else:
        logger.warning(
            "manifest_writer: provenance undetermined — "
            f"{manifest['head_consistency']['reason']}"
        )
