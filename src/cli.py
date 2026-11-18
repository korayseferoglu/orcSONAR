"""orcSONAR command-line interface.

Usage:
    python -m src.cli --gene VEGFA --cell-line HeLa \\
        --sarna-sequence GCAACCATAGCCTCGGCCGC

Invokes the full Snakemake pipeline with a tqdm progress bar that tracks
completed Snakemake jobs in real time.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

_SUPPORTED_CELL_LINES = [
    "A549", "GM12878", "HEK293T", "HeLa", "HepG2", "Huh7", "K562", "MCF7"
]

_TOTAL_JOBS = 32  # from dry-run output (tss_mapping → generate_report)

_STAGE_LABELS: dict[str, str] = {
    "tss_mapping":          "Stage 1 — TSS mapping",
    "transcript_resolution":"Stage 1 — transcript resolution",
    "promoter_definition":  "Stage 1 — promoter definition",
    "mirbase_check":        "Stage 2 — miRBase check",
    "seed_alignment":       "Stage 2 — seed alignment",
    "repeat_scan":          "Stage 2 — repeat scan",
    "merge_offtargets":     "Stage 2 — merging off-targets",
    "cosmic_scan":          "Stage 3 — COSMIC scan",
    "gnomad_query":         "Stage 3 — gnomAD query",
    "clinvar_check":        "Stage 3 — ClinVar check",
    "phylop_score":         "Stage 3 — phyloP conservation",
    "merge_variants":       "Stage 3 — merging variants",
    "atac_signal":          "Stage 4 — ATAC-seq signal",
    "histone_marks":        "Stage 4 — histone marks",
    "groseq_signal":        "Stage 4 — GRO-seq signal",
    "hic_contacts":         "Stage 4 — Hi-C contacts",
    "ccle_expression":      "Stage 4 — CCLE expression",
    "merge_epigenetic":     "Stage 4 — merging epigenetic",
    "delta_g":              "Stage 5 — ΔG thermodynamics",
    "shape_profile":        "Stage 5 — SHAPE accessibility",
    "m6a_mapping":          "Stage 5 — m6A sites",
    "adar_risk":            "Stage 5 — ADAR risk",
    "g4_detection":         "Stage 5 — G4 quadruplexes",
    "merge_biophysics":     "Stage 5 — merging biophysics",
    "ago2_loading":         "Stage 6 — Ago2 loading",
    "rbp_competition":      "Stage 6 — RBP competition",
    "circrna_sponge":       "Stage 6 — circRNA sponge",
    "immune_screen":        "Stage 6 — immune screen",
    "merge_execution":      "Stage 6 — merging execution",
    "score_integration":    "Stage 7 — score integration",
    "risk_classification":  "Stage 7 — risk classification",
    "generate_report":      "Stage 7 — generating report",
}

_RULE_RE = re.compile(r"^rule\s+(\w+):", re.MULTILINE)
_JOB_DONE_RE = re.compile(r"^\d+ of \d+ steps.*done", re.MULTILINE)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="orcsonar",
        description=(
            "orcSONAR — Cell-specific, biophysics-based saRNA off-target predictor.\n"
            "Integrates epigenetic, variant, and thermodynamic data to predict RISC\n"
            "off-target risk in a chosen human cell line."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.cli --gene VEGFA --cell-line HeLa \\\n"
            "      --sarna-sequence GCAACCATAGCCTCGGCCGC\n"
            "\n"
            "  python -m src.cli --gene TP53 --cell-line A549 \\\n"
            "      --sarna-sequence GCAACCATAGCCTCGGCCGC \\\n"
            "      --config config/config.yaml --cores 8\n"
        ),
    )

    p.add_argument(
        "--gene", required=True,
        metavar="SYMBOL",
        help="HGNC gene symbol of the saRNA target (e.g., VEGFA, TP53).",
    )
    p.add_argument(
        "--cell-line", required=True,
        choices=_SUPPORTED_CELL_LINES,
        metavar="CELL_LINE",
        help=f"Target cell line. Supported: {', '.join(_SUPPORTED_CELL_LINES)}.",
    )
    p.add_argument(
        "--sarna-sequence", required=True,
        metavar="SEQ",
        help=(
            "saRNA guide strand sequence (DNA or RNA, 10–30 nt). "
            "T is automatically converted to U."
        ),
    )
    p.add_argument(
        "--config", default="config/config.yaml",
        metavar="FILE",
        help="Path to config YAML (default: config/config.yaml).",
    )
    p.add_argument(
        "--output-dir", default="results",
        metavar="DIR",
        help="Pipeline results directory (default: results).",
    )
    p.add_argument(
        "--cores", default=4, type=int,
        metavar="N",
        help="CPU cores to use (default: 4).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the execution plan without running any jobs.",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-job Snakemake output (only show progress bar).",
    )
    return p


def _validate_sequence(seq: str) -> str:
    cleaned = seq.upper().replace("T", "U")
    invalid = set(cleaned) - set("ACGU")
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Invalid bases in --sarna-sequence: {sorted(invalid)}. "
            "Only A/C/G/U (or T) are allowed."
        )
    if not (10 <= len(cleaned) <= 30):
        raise argparse.ArgumentTypeError(
            f"--sarna-sequence must be 10–30 nt, got {len(cleaned)}."
        )
    return cleaned


def _purge_stale_cache(config_path: str) -> None:
    """Drop cache entries written by an older schema version, and say so.

    Called once before Snakemake starts, so a run that suddenly goes back to
    the network has a line explaining why (roadmap B0). `Cache.get` already
    refuses a stale entry on its own; this exists to make the invalidation
    visible instead of silent.

    Never fails the run: a cache that cannot be purged is still correct,
    because the per-read check stands on its own. The failure is logged rather
    than swallowed.

    Args:
        config_path: Path to the YAML config naming the cache database.
    """
    from loguru import logger

    from src.core.cache import Cache
    from src.core.config import load_config

    try:
        cfg = load_config(config_path)
        with Cache(cfg.data_paths.cache_db) as cache:
            cache.purge_stale()
    except Exception as exc:  # noqa: BLE001 - never block a run over the cache
        logger.warning(
            f"cli: could not purge the cache ({type(exc).__name__}: {exc}). "
            "Stale entries are still refused per read, so the run is unaffected."
        )


def _run_pipeline(args: argparse.Namespace) -> int:
    """Invoke Snakemake and stream output through a tqdm progress bar.

    Returns:
        Snakemake process exit code.
    """
    cell_line_norm = args.cell_line.replace(" ", "")
    target = str(
        Path(args.output_dir) / f"{args.gene}_{cell_line_norm}" / "final_report.html"
    )

    sarna_dna = args.sarna_sequence.replace("U", "T")

    cmd = [
        sys.executable, "-m", "snakemake",
        target,
        "--cores", str(args.cores),
        "--configfile", args.config,
        "--config",
            f"target_gene={args.gene}",
            f"cell_line={cell_line_norm}",
            f"sarna_sequence={sarna_dna}",
            f"results_dir={args.output_dir}",
    ]

    if args.dry_run:
        cmd.append("--dry-run")
    else:
        _purge_stale_cache(args.config)
    if args.quiet:
        cmd.extend(["--quiet", "all"])

    print(
        f"\norcSONAR — {args.gene} / {cell_line_norm}\n"
        f"  saRNA : {args.sarna_sequence}\n"
        f"  target: {target}\n"
        f"  cores : {args.cores}\n"
    )

    if args.dry_run:
        result = subprocess.run(cmd)
        return result.returncode

    completed_jobs: set[str] = set()

    with tqdm(
        total=_TOTAL_JOBS,
        desc="Initialising",
        unit="job",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} jobs [{elapsed}<{remaining}]",
        ncols=80,
    ) as pbar:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:  # type: ignore[union-attr]
            line_s = line.rstrip()

            for rule_name, label in _STAGE_LABELS.items():
                if (
                    rule_name in line_s
                    and rule_name not in completed_jobs
                    and any(kw in line_s for kw in ("Finished", "Done", "rule " + rule_name))
                ):
                    completed_jobs.add(rule_name)
                    pbar.set_description(label[:45])
                    pbar.update(1)
                    break

            if not args.quiet:
                tqdm.write(line_s)

        proc.wait()

        if proc.returncode == 0:
            pbar.set_description("Complete")
            pbar.update(max(0, _TOTAL_JOBS - pbar.n))

    return proc.returncode


def main() -> None:
    """Entry point for the orcsonar CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    try:
        args.sarna_sequence = _validate_sequence(args.sarna_sequence)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if not Path(args.config).exists():
        parser.error(f"Config file not found: {args.config}")

    rc = _run_pipeline(args)

    if rc == 0:
        cell_line_norm = args.cell_line.replace(" ", "")
        report = Path(args.output_dir) / f"{args.gene}_{cell_line_norm}" / "final_report.html"
        if not args.dry_run:
            print(f"\nDone. Report: {report.resolve()}")
    else:
        print(f"\nPipeline failed (exit code {rc}).", file=sys.stderr)
        sys.exit(rc)


if __name__ == "__main__":
    main()
