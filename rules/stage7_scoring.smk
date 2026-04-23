# Stage 7 — Scoring & Reporting
# score_integration waits for all four parallel merge outputs (stages 3–6).
# Sequential: score_integration → risk_classification → generate_report

rule score_integration:
    """Compute weighted domain scores for each off-target site.

    Weights from config (must sum to 1.0):
      sequence_specificity (0.20) + variant_toxicity (0.15)
      + biophysics_structure (0.25) + epigenetic_context (0.20)
      + execution_safety (0.20)
    """
    input:
        offtargets  = "results/{gene}_{cell_line}/stage2_offtargets.json",
        variants    = "results/{gene}_{cell_line}/stage3_variants.json",
        epigenetic  = "results/{gene}_{cell_line}/stage4_epigenetic.json",
        biophysics  = "results/{gene}_{cell_line}/stage5_biophysics.json",
        execution   = "results/{gene}_{cell_line}/stage6_execution.json",
    output:
        "results/{gene}_{cell_line}/stage7_scores.json",
    log:
        "logs/{gene}_{cell_line}/score_integration.log",
    params:
        weights = config["scoring_weights"],
    run:
        from src.scoring import score_integrator
        score_integrator.run(
            offtargets_path=input.offtargets,
            variants_path=input.variants,
            epigenetic_path=input.epigenetic,
            biophysics_path=input.biophysics,
            execution_path=input.execution,
            weights=params.weights,
            output_path=output[0],
            log_path=log[0],
        )


rule risk_classification:
    """Classify each off-target site into SAFE / WARNING / HIGH_RISK / DANGEROUS.

    Risk thresholds from config:
      [0.0, 0.30) → SAFE
      [0.30, 0.60) → WARNING
      [0.60, 0.80) → HIGH_RISK
      [0.80, 1.00] → DANGEROUS
    """
    input:
        scores = "results/{gene}_{cell_line}/stage7_scores.json",
    output:
        "results/{gene}_{cell_line}/stage7_classification.json",
    log:
        "logs/{gene}_{cell_line}/risk_classification.log",
    params:
        thresholds = config["risk_thresholds"],
    run:
        from src.scoring import risk_classifier
        risk_classifier.run(
            scores_path=input.scores,
            thresholds=params.thresholds,
            output_path=output[0],
            log_path=log[0],
        )


rule generate_report:
    """Generate final JSON summary and HTML report (Jinja2 + WeasyPrint)."""
    input:
        classification = "results/{gene}_{cell_line}/stage7_classification.json",
        scores         = "results/{gene}_{cell_line}/stage7_scores.json",
        offtargets     = "results/{gene}_{cell_line}/stage2_offtargets.json",
        variants       = "results/{gene}_{cell_line}/stage3_variants.json",
        epigenetic     = "results/{gene}_{cell_line}/stage4_epigenetic.json",
        biophysics     = "results/{gene}_{cell_line}/stage5_biophysics.json",
        execution      = "results/{gene}_{cell_line}/stage6_execution.json",
    output:
        json_report = "results/{gene}_{cell_line}/final_report.json",
        html_report = "results/{gene}_{cell_line}/final_report.html",
    log:
        "logs/{gene}_{cell_line}/generate_report.log",
    params:
        gene      = lambda wc: wc.gene,
        cell_line = lambda wc: wc.cell_line,
        sarna     = config["sarna_sequence"],
    run:
        from src.reporting import report_generator
        report_generator.run(
            classification_path=input.classification,
            scores_path=input.scores,
            offtargets_path=input.offtargets,
            variants_path=input.variants,
            epigenetic_path=input.epigenetic,
            biophysics_path=input.biophysics,
            execution_path=input.execution,
            gene=params.gene,
            cell_line=params.cell_line,
            sarna_sequence=params.sarna,
            json_output=output.json_report,
            html_output=output.html_report,
            log_path=log[0],
        )
