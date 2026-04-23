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
RESULTS   = Path("results") / f"{GENE}_{CELL_LINE}"

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
            "results/{gene}_{cell_line}/final_report.html",
            gene=GENE,
            cell_line=CELL_LINE,
        )
