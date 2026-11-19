# Stage 4 — Epigenetic & Topology
# Parallel with stages 3, 5, 6 — all start from stage2_offtargets.json.
# ENCODE BigWig streams are cell-line-specific (config/cell_lines.yaml).
# atac_signal, histone_marks, groseq_signal, hic_contacts, ccle_expression → merge_epigenetic.

rule atac_signal:
    """Extract ATAC-seq signal at off-target regions from cell-line-specific BigWig."""
    input:
        offtargets = RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_atac.json",
    log:
        "logs/{gene}_{cell_line}/atac_signal.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage4_epigenetic import atac_fetcher
        atac_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
            config_raw=config,
        )


rule histone_marks:
    """Extract H3K4me3 and H3K27ac ChIP-seq signal from cell-line-specific BigWigs."""
    input:
        offtargets = RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_histones.json",
    log:
        "logs/{gene}_{cell_line}/histone_marks.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage4_epigenetic import histone_fetcher
        histone_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
            config_raw=config,
        )


rule groseq_signal:
    """Extract GRO-seq / PRO-seq nascent transcription signal from BigWig."""
    input:
        offtargets = RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_groseq.json",
    log:
        "logs/{gene}_{cell_line}/groseq_signal.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage4_epigenetic import groseq_fetcher
        groseq_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
            config_raw=config,
        )


rule hic_contacts:
    """Extract Hi-C contact frequency at off-target loci using hic-straw."""
    input:
        offtargets = RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_hic.json",
    log:
        "logs/{gene}_{cell_line}/hic_contacts.log",
    params:
        cell_lines_cfg = "config/cell_lines.yaml",
    run:
        from src.stage4_epigenetic import hic_fetcher
        hic_fetcher.run(
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            cell_lines_cfg=params.cell_lines_cfg,
            output_path=output[0],
            log_path=log[0],
            config_raw=config,
        )


rule ccle_expression:
    """Look up gene expression in target cell line from CCLE CSV (lazy load)."""
    input:
        ccle_csv   = config["data_paths"]["ccle_csv"],
        offtargets = RESULTS_DIR + "/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_ccle.json",
    log:
        "logs/{gene}_{cell_line}/ccle_expression.log",
    run:
        from src.stage4_epigenetic import ccle_reader
        ccle_reader.run(
            ccle_csv=input.ccle_csv,
            offtargets_path=input.offtargets,
            cell_line=wildcards.cell_line,
            output_path=output[0],
            log_path=log[0],
            config_raw=config,
        )


rule merge_epigenetic:
    """Merge ATAC, histone, GRO-seq, Hi-C, CCLE into per-site EpigeneticScore objects."""
    input:
        atac     = RESULTS_DIR + "/{gene}_{cell_line}/stage4_atac.json",
        histones = RESULTS_DIR + "/{gene}_{cell_line}/stage4_histones.json",
        groseq   = RESULTS_DIR + "/{gene}_{cell_line}/stage4_groseq.json",
        hic      = RESULTS_DIR + "/{gene}_{cell_line}/stage4_hic.json",
        ccle     = RESULTS_DIR + "/{gene}_{cell_line}/stage4_ccle.json",
    output:
        RESULTS_DIR + "/{gene}_{cell_line}/stage4_epigenetic.json",
    log:
        "logs/{gene}_{cell_line}/merge_epigenetic.log",
    run:
        from src.stage4_epigenetic import epigenetic_merger
        epigenetic_merger.run(
            atac_path=input.atac,
            histones_path=input.histones,
            groseq_path=input.groseq,
            hic_path=input.hic,
            ccle_path=input.ccle,
            output_path=output[0],
            log_path=log[0],
        )
