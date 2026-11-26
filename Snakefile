# orcSONAR — Main Snakemake Pipeline
# Parallelism note:
#   Stage 1 sequential: tss_mapping → transcript_resolution → promoter_definition
#   Stage 2 sequential: seed_alignment → [mirbase_check parallel] → repeat_scan → merge_offtargets
#   Stages 3, 4, 5, 6 run IN PARALLEL after stage 2 completes (all depend only on stage2_offtargets.json)
#   Stage 7 waits for all four merge outputs before scoring.

from pathlib import Path

configfile: "config/config.yaml"

GENE      = config["target_gene"]
CELL_LINE = config["cell_line"]

# Every rule builds its paths from this prefix. It was hardcoded to "results"
# in 89 places while `--output-dir` was accepted by the CLI, documented in the
# README and passed through as `results_dir` -- which no rule read, so the flag
# raised MissingRuleException and there was no supported way to run without
# overwriting the reference runs (audit 2026-11-19, Bulgu 11).
# Rules concatenate rather than f-string it, so the {gene}/{cell_line}
# wildcards stay literal and need no escaping.
RESULTS_DIR = config.get("results_dir", "results")

include: "rules/stage1_genomic.smk"
include: "rules/stage2_offtarget.smk"
include: "rules/stage3_variant.smk"
include: "rules/stage4_epigenetic.smk"
include: "rules/stage5_biophysics.smk"
include: "rules/stage6_execution.smk"
include: "rules/stage7_scoring.smk"


rule all:
    input:
        expand(
            RESULTS_DIR + "/{gene}_{cell_line}/final_report.html",
            gene=GENE,
            cell_line=CELL_LINE,
        ),
        # Roadmap H10. In `all` on purpose: a run without provenance is an
        # orphan, and making the manifest optional is how it stops being
        # written.
        expand(
            RESULTS_DIR + "/{gene}_{cell_line}/manifest.json",
            gene=GENE,
            cell_line=CELL_LINE,
        )
