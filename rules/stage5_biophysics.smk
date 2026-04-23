# Stage 5 — Biophysics & Structural
# Parallel with stages 3, 4, 6 — all start from stage2_offtargets.json.
# delta_g, shape_profile, m6a_mapping, adar_risk, g4_detection → merge_biophysics.

rule delta_g:
    """Compute RNA:DNA hybrid free energy (ΔG) using Turner nearest-neighbour rules."""
    input:
        offtargets  = "results/{gene}_{cell_line}/stage2_offtargets.json",
        turner_dir  = config["data_paths"]["turner_rules_dir"],
    output:
        "results/{gene}_{cell_line}/stage5_deltag.json",
    log:
        "logs/{gene}_{cell_line}/delta_g.log",
    params:
        sarna          = config["sarna_sequence"],
        dg_strong      = config["delta_g_strong"],
        dg_moderate    = config["delta_g_moderate"],
    run:
        from src.stage5_biophysics import delta_g_calculator
        delta_g_calculator.run(
            sarna_sequence=params.sarna,
            offtargets_path=input.offtargets,
            turner_dir=input.turner_dir,
            dg_strong=params.dg_strong,
            dg_moderate=params.dg_moderate,
            output_path=output[0],
            log_path=log[0],
        )


rule shape_profile:
    """Retrieve SHAPE-seq accessibility scores for off-target regions."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
        shape_dir  = config["data_paths"]["shape_seq_dir"],
    output:
        "results/{gene}_{cell_line}/stage5_shape.json",
    log:
        "logs/{gene}_{cell_line}/shape_profile.log",
    run:
        from src.stage5_biophysics import shape_reader
        shape_reader.run(
            offtargets_path=input.offtargets,
            shape_dir=input.shape_dir,
            cell_line=wildcards.cell_line,
            output_path=output[0],
            log_path=log[0],
        )


rule m6a_mapping:
    """Identify m6A modification sites overlapping off-target regions (tabix)."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
        m6a_bed    = config["data_paths"]["m6a_bed"],
    output:
        "results/{gene}_{cell_line}/stage5_m6a.json",
    log:
        "logs/{gene}_{cell_line}/m6a_mapping.log",
    run:
        from src.stage5_biophysics import m6a_mapper
        m6a_mapper.run(
            offtargets_path=input.offtargets,
            m6a_bed=input.m6a_bed,
            cell_line=wildcards.cell_line,
            output_path=output[0],
            log_path=log[0],
        )


rule adar_risk:
    """Estimate A-to-I editing risk via Alu-repeat proxy (RepeatMasker/UCSC API)."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage5_adar.json",
    log:
        "logs/{gene}_{cell_line}/adar_risk.log",
    params:
        ucsc_url = config["ucsc_api_url"],
    run:
        from src.stage5_biophysics import adar_estimator
        adar_estimator.run(
            offtargets_path=input.offtargets,
            ucsc_api_url=params.ucsc_url,
            output_path=output[0],
            log_path=log[0],
        )


rule g4_detection:
    """Detect G-quadruplex motifs in off-target sequences via regex."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage5_g4.json",
    log:
        "logs/{gene}_{cell_line}/g4_detection.log",
    run:
        from src.stage5_biophysics import g4_detector
        g4_detector.run(
            offtargets_path=input.offtargets,
            output_path=output[0],
            log_path=log[0],
        )


rule merge_biophysics:
    """Merge ΔG, SHAPE, m6A, ADAR, G4 into per-site BiophysicsScore objects."""
    input:
        deltag = "results/{gene}_{cell_line}/stage5_deltag.json",
        shape  = "results/{gene}_{cell_line}/stage5_shape.json",
        m6a    = "results/{gene}_{cell_line}/stage5_m6a.json",
        adar   = "results/{gene}_{cell_line}/stage5_adar.json",
        g4     = "results/{gene}_{cell_line}/stage5_g4.json",
    output:
        "results/{gene}_{cell_line}/stage5_biophysics.json",
    log:
        "logs/{gene}_{cell_line}/merge_biophysics.log",
    run:
        from src.stage5_biophysics import biophysics_merger
        biophysics_merger.run(
            deltag_path=input.deltag,
            shape_path=input.shape,
            m6a_path=input.m6a,
            adar_path=input.adar,
            g4_path=input.g4,
            output_path=output[0],
            log_path=log[0],
        )
