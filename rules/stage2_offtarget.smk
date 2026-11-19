# Stage 2 — Off-Target Scan
# seed_alignment and mirbase_check run independently (parallel).
# repeat_scan depends on seed_hits. merge_offtargets waits for all three.

rule seed_alignment:
    """Whole-transcriptome seed alignment (7-nt seed, max 3 mismatches)."""
    input:
        promoter = RESULTS_DIR + "/{gene}_{cell_line}/stage1_promoter.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage2_seed_hits.json",
    log:
        "logs/{gene}_{cell_line}/seed_alignment.log",
    params:
        sarna      = config["sarna_sequence"],
        seed_len   = config["seed_length"],
        max_mm     = config["max_mismatches"],
        gc_range   = config["gc_range"],
    threads: 4
    run:
        from src.stage2_offtarget_scan import seed_aligner
        seed_aligner.run(
            sarna_sequence=params.sarna,
            promoter_path=input.promoter,
            seed_length=params.seed_len,
            max_mismatches=params.max_mm,
            gc_range=params.gc_range,
            threads=threads,
            output_path=output[0],
            log_path=log[0],
            cell_line=wildcards.cell_line,
        )


rule mirbase_check:
    """Check saRNA sequence against human miRBase entries."""
    input:
        mirbase = config["data_paths"]["mirbase_fa"],
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage2_mirbase.json",
    log:
        "logs/{gene}_{cell_line}/mirbase_check.log",
    params:
        sarna = config["sarna_sequence"],
    run:
        from src.stage2_offtarget_scan import mirbase_checker
        mirbase_checker.run(
            sarna_sequence=params.sarna,
            mirbase_fa=input.mirbase,
            output_path=output[0],
            log_path=log[0],
        )


rule repeat_scan:
    """Annotate seed hits overlapping RepeatMasker elements (UCSC API)."""
    input:
        seed_hits = RESULTS_DIR + "/{gene}_{cell_line}/stage2_seed_hits.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage2_repeats.json",
    log:
        "logs/{gene}_{cell_line}/repeat_scan.log",
    params:
        ucsc_url = config["ucsc_api_url"],
    run:
        from src.stage2_offtarget_scan import repeat_scanner
        repeat_scanner.run(
            seed_hits_path=input.seed_hits,
            ucsc_api_url=params.ucsc_url,
            output_path=output[0],
            log_path=log[0],
        )


rule merge_offtargets:
    """Merge seed hits, miRNA overlaps, and repeat annotations into unified off-target list."""
    input:
        seed_hits = RESULTS_DIR + "/{gene}_{cell_line}/stage2_seed_hits.json",
        mirbase   = RESULTS_DIR + "/{gene}_{cell_line}/stage2_mirbase.json",
        repeats   = RESULTS_DIR + "/{gene}_{cell_line}/stage2_repeats.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    log:
        "logs/{gene}_{cell_line}/merge_offtargets.log",
    run:
        from src.stage2_offtarget_scan import offtarget_merger
        offtarget_merger.run(
            seed_hits_path=input.seed_hits,
            mirbase_path=input.mirbase,
            repeats_path=input.repeats,
            output_path=output[0],
            log_path=log[0],
        )
