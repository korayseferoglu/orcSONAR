# Stage 1 — Genomic Map
# Sequential: tss_mapping → transcript_resolution → promoter_definition
# Inputs: EPDnew BED, FANTOM5 BED (local); Ensembl/RefSeq (REST API)

rule tss_mapping:
    """Map TSS positions for the target gene from EPDnew and FANTOM5."""
    input:
        epdnew  = config["data_paths"]["epdnew_bed"],
        fantom5 = config["data_paths"]["fantom5_bed"],
    output:
        "results/{gene}_{cell_line}/stage1_tss.json",
    log:
        "logs/{gene}_{cell_line}/tss_mapping.log",
    params:
        gene = lambda wc: wc.gene,
    run:
        from src.stage1_genomic_map import tss_mapper
        tss_mapper.run(
            gene=wildcards.gene,
            epdnew_bed=input.epdnew,
            fantom5_bed=input.fantom5,
            output_path=output[0],
            log_path=log[0],
        )


rule transcript_resolution:
    """Fetch all transcripts for the target gene via Ensembl/RefSeq REST API."""
    output:
        "results/{gene}_{cell_line}/stage1_transcripts.json",
    log:
        "logs/{gene}_{cell_line}/transcript_resolution.log",
    params:
        ensembl_url = config["ensembl_base_url"],
        ncbi_url    = config["ncbi_eutils_url"],
    run:
        from src.stage1_genomic_map import transcript_resolver
        transcript_resolver.run(
            gene=wildcards.gene,
            ensembl_url=params.ensembl_url,
            ncbi_url=params.ncbi_url,
            output_path=output[0],
            log_path=log[0],
        )


rule promoter_definition:
    """Define promoter windows around each TSS using upstream/downstream config."""
    input:
        tss         = "results/{gene}_{cell_line}/stage1_tss.json",
        transcripts = "results/{gene}_{cell_line}/stage1_transcripts.json",
    output:
        "results/{gene}_{cell_line}/stage1_promoter.json",
    log:
        "logs/{gene}_{cell_line}/promoter_definition.log",
    params:
        upstream   = config["promoter_upstream"],
        downstream = config["promoter_downstream"],
    run:
        from src.stage1_genomic_map import promoter_definer
        promoter_definer.run(
            tss_path=input.tss,
            transcripts_path=input.transcripts,
            upstream=params.upstream,
            downstream=params.downstream,
            output_path=output[0],
            log_path=log[0],
        )
