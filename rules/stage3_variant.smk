# Stage 3 — Variant & Toxicity
# Parallel with stages 4, 5, 6 — all start from stage2_offtargets.json.
# cosmic_scan, gnomad_query, clinvar_check, phylop_score → merge_variants.

rule cosmic_scan:
    """Query COSMIC VCF (tabix-indexed) for mutations in off-target regions."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
        cosmic_vcf = config["data_paths"]["cosmic_vcf"],
    output:
        "results/{gene}_{cell_line}/stage3_cosmic.json",
    log:
        "logs/{gene}_{cell_line}/cosmic_scan.log",
    run:
        from src.stage3_variant_tox import cosmic_scanner
        cosmic_scanner.run(
            offtargets_path=input.offtargets,
            cosmic_vcf=input.cosmic_vcf,
            output_path=output[0],
            log_path=log[0],
        )


rule gnomad_query:
    """Query gnomAD v4 GraphQL API for population allele frequencies."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage3_gnomad.json",
    log:
        "logs/{gene}_{cell_line}/gnomad_query.log",
    params:
        api_url = config["gnomad_api_url"],
    run:
        from src.stage3_variant_tox import gnomad_client
        gnomad_client.run(
            offtargets_path=input.offtargets,
            api_url=params.api_url,
            output_path=output[0],
            log_path=log[0],
        )


rule clinvar_check:
    """Query NCBI ClinVar for pathogenic variants in off-target regions."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage3_clinvar.json",
    log:
        "logs/{gene}_{cell_line}/clinvar_check.log",
    params:
        ncbi_url = config["ncbi_eutils_url"],
    run:
        from src.stage3_variant_tox import clinvar_client
        clinvar_client.run(
            offtargets_path=input.offtargets,
            ncbi_url=params.ncbi_url,
            output_path=output[0],
            log_path=log[0],
        )


rule phylop_score:
    """Fetch phyloP conservation scores from UCSC remote BigWig."""
    input:
        offtargets = "results/{gene}_{cell_line}/stage2_offtargets.json",
    output:
        "results/{gene}_{cell_line}/stage3_phylop.json",
    log:
        "logs/{gene}_{cell_line}/phylop_score.log",
    params:
        bigwig_url = config["phylop_bigwig_url"],
    run:
        from src.stage3_variant_tox import phylop_fetcher
        phylop_fetcher.run(
            offtargets_path=input.offtargets,
            bigwig_url=params.bigwig_url,
            output_path=output[0],
            log_path=log[0],
        )


rule merge_variants:
    """Merge COSMIC, gnomAD, ClinVar, phyloP into per-site VariantScore objects."""
    input:
        cosmic  = "results/{gene}_{cell_line}/stage3_cosmic.json",
        gnomad  = "results/{gene}_{cell_line}/stage3_gnomad.json",
        clinvar = "results/{gene}_{cell_line}/stage3_clinvar.json",
        phylop  = "results/{gene}_{cell_line}/stage3_phylop.json",
    output:
        "results/{gene}_{cell_line}/stage3_variants.json",
    log:
        "logs/{gene}_{cell_line}/merge_variants.log",
    run:
        from src.stage3_variant_tox import variant_merger
        variant_merger.run(
            cosmic_path=input.cosmic,
            gnomad_path=input.gnomad,
            clinvar_path=input.clinvar,
            phylop_path=input.phylop,
            output_path=output[0],
            log_path=log[0],
        )
