# Stage 6 — Execution & Safety
# Parallel with stages 3, 4, 5 — all start from stage2_offtargets.json.
# ago2_loading, rbp_competition, circrna_sponge, immune_screen → merge_execution.

rule ago2_loading:
    """Extract Ago2 eCLIP signal at off-target regions from cell-line-specific BigWig."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage6_ago2.json",
    log:
        "logs/{gene}_{cell_line}/ago2_loading.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage6_execution import ago2_fetcher
        ago2_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
        )


rule rbp_competition:
    """Extract hnRNPA1 eCLIP (POSTAR3 proxy) signal for RBP competition assessment."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage6_rbp.json",
    log:
        "logs/{gene}_{cell_line}/rbp_competition.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage6_execution import rbp_fetcher
        rbp_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
        )


rule circrna_sponge:
    """Check for circRNA sponge overlap with off-target regions (circAtlas)."""
    input:
        offtargets  = "results/{gene}_{cell_line}/stage2_offtargets.json",
        circrna_dir = config["data_paths"]["circrna_dir"],
    output:
        "results/{gene}_{cell_line}/stage6_circrna.json",
    log:
        "logs/{gene}_{cell_line}/circrna_sponge.log",
    run:
        from src.stage6_execution import circrna_checker
        circrna_checker.run(
            offtargets_path=input.offtargets,
            circrna_dir=input.circrna_dir,
            output_path=output[0],
            log_path=log[0],
        )


rule immune_screen:
    """Screen saRNA and off-target sequences for TLR7/TLR8 immune danger motifs."""
    input:
        offtargets    = "results/{gene}_{cell_line}/stage2_offtargets.json",
        immune_motifs = config["data_paths"]["immune_motifs"],
    output:
        "results/{gene}_{cell_line}/stage6_immune.json",
    log:
        "logs/{gene}_{cell_line}/immune_screen.log",
    params:
        sarna = config["sarna_sequence"],
    run:
        from src.stage6_execution import immune_screener
        immune_screener.run(
            sarna_sequence=params.sarna,
            offtargets_path=input.offtargets,
            immune_motifs_file=input.immune_motifs,
            output_path=output[0],
            log_path=log[0],
        )


rule merge_execution:
    """Merge Ago2, RBP, circRNA, immune into per-site ExecutionScore objects."""
    input:
        ago2    = "results/{gene}_{cell_line}/stage6_ago2.json",
        rbp     = "results/{gene}_{cell_line}/stage6_rbp.json",
        circrna = "results/{gene}_{cell_line}/stage6_circrna.json",
        immune  = "results/{gene}_{cell_line}/stage6_immune.json",
    output:
        "results/{gene}_{cell_line}/stage6_execution.json",
    log:
        "logs/{gene}_{cell_line}/merge_execution.log",
    run:
        from src.stage6_execution import execution_merger
        execution_merger.run(
            ago2_path=input.ago2,
            rbp_path=input.rbp,
            circrna_path=input.circrna,
            immune_path=input.immune,
            output_path=output[0],
            log_path=log[0],
        )
