---
name: orcsonar-data-sources
description: Reference for orcSONAR's 24 genomic data sources — which source feeds which pipeline stage, on-disk paths under data/, file-format and column layouts (BED6, BED9, VCF, FASTA, CSV, Turner .dg/.dat), chr-prefix and coordinate-base conventions, tabix-indexed files, and the REST/GraphQL/BigWig endpoints with their rate limits. Load this when parsing or writing code against EPDnew, FANTOM5 CAGE, miRBase, COSMIC, CCLE/DepMap, m6A-Atlas/RMBase, circAtlas, Turner rules, SHAPE-seq or immune-motif files; when querying Ensembl REST, NCBI E-utilities, UCSC RepeatMasker, gnomAD GraphQL, ENCODE or 4DN; when streaming remote BigWig or .hic; when adding a data source or a cell line; or when debugging a genomic query that returns empty, off-by-one or misaligned results and you need to know whether a coordinate needs a "chr" prefix added or stripped.
---

# orcSONAR data sources

24 sources across five groups. Full registry, format samples and per-cell-line
coverage: read `docs/DATA_SOURCES.md` (§2 registry, §4 format samples,
§7 cell-line coverage). Paths are never hardcoded — they come from
`data_paths` in `config/config.yaml`. Per-cell-line source wiring lives in
`config/cell_lines.yaml` and `config/ccle_depmap_ids.yaml`.

## Coordinate conventions — the main source of silent bugs

| Source | Chromosome naming |
|---|---|
| COSMIC VCF | **No `chr` prefix** — `1`, `2`, `X`. Strip `chr` before querying. |
| m6A BED, EPDnew, FANTOM5, circAtlas BED | **Has `chr` prefix** |
| Remote BigWig (ENCODE, UCSC) | **Has `chr` prefix** |

- BED is 0-based half-open `[start, end)`; VCF is 1-based inclusive.
- `hicstraw` queries must be **snapped to the bin boundary** of the requested
  resolution — an unaligned start silently returns an empty contact list
  instead of an error.
- All coordinates are hg38/GRCh38, without exception.
- Tabix-indexed (query by region, never read whole): COSMIC `.vcf.gz` + `.tbi`,
  m6A `.bed.gz` + `.tbi`. CCLE CSV is ~291 MB — lazy-load, never read whole.
- miRBase sequences use `U`, not `T`; filter to the `hsa-` prefix for human.

## Access types

| Type | Count | Source numbers (as numbered in docs/DATA_SOURCES.md §2) |
|---|---|---|
| Local file | 10 | 1, 2, 5, 7, 15, 16, 17, 18, 23, 24 |
| REST / GraphQL API | 5 | 3, 4, 6, 8, 9 |
| Remote BigWig / `.hic` stream | 7 | 10, 11, 12, 13, 14, 21, 22 |
| Computed from another source | 2 | 19 (ADAR via Alu proxy), 20 (G4 via regex) |

## Which source feeds which stage

| Stage | Sources |
|---|---|
| 1 Genomic map | EPDnew (local BED), FANTOM5 CAGE (local BED), Ensembl/GENCODE (REST), NCBI RefSeq (REST) |
| 2 Off-target scan | miRBase (local FASTA), RepeatMasker (UCSC REST), Ensembl transcript sequences (REST) |
| 3 Variant & toxicity | COSMIC (local tabix VCF), gnomAD (GraphQL), ClinVar (NCBI REST), phyloP 100way (remote BigWig) |
| 4 Epigenetic & topology | ENCODE ATAC-seq, ENCODE ChIP-seq (H3K4me3, H3K27ac, H3K27me3), GRO-/PRO-seq (all remote BigWig), Hi-C 4DN (remote `.hic`), CCLE (local CSV) |
| 5 Biophysics & structural | Turner rules (local `.dg`/`.dat`), SHAPE-seq/icSHAPE (local), m6A-Atlas (local tabix BED), ADAR (computed from RepeatMasker), G4 (regex) |
| 6 Execution & safety | ENCODE Ago2 eCLIP, ENCODE RBP eCLIP (hnRNPA1 etc.) — both remote BigWig; circAtlas (local BED), immune motifs (local text) |

Remote ENCODE/4DN sources are per cell line; accessions are in
`config/cell_lines.yaml`. Supported: A549, GM12878, HEK293T, HeLa, HepG2, Huh7,
K562, MCF7. Not every cell line has every signal — see `docs/DATA_SOURCES.md` §7.

## API endpoints and rate limits

| Endpoint | URL | Limit |
|---|---|---|
| Ensembl REST | `https://rest.ensembl.org` | 15 req/s |
| NCBI E-utilities | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | 3 req/s (10 with key) |
| UCSC (RepeatMasker) | `https://api.genome.ucsc.edu/getData/track?genome=hg38&track=rmsk` | 5 req/s |
| gnomAD GraphQL | `https://gnomad.broadinstitute.org/api` | **1 req/s** — `gnomad_client.py` paces itself at 1 Hz and backs off on 429, regardless of the higher value in `config.yaml` |
| ENCODE portal | `https://www.encodeproject.org` | — |
| phyloP BigWig | `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw` | remote stream |

Known API quirks:

- **gnomAD v4 GraphQL**: `region(...)` requires `reference_genome: GRCh38` and no
  longer accepts `dataset`; `dataset: gnomad_r4` moved to the inner
  `Region.variants(...)` field. Both are enums — no quotes.
- **ENCODE BigWig** URLs answer with a 307 redirect; `encode_reader.py` resolves
  it before handing the URL to pyBigWig, which does not follow redirects.
- **pyBigWig** must be built with libcurl support for remote access; the plain
  pip wheel cannot open an https URL.

All API calls go through `tenacity` retry and are cached in SQLite under
`data/cache/`. On any source failure: log a warning and fall back to the neutral
score (0.5) rather than aborting — but note that a report produced with several
sources unavailable is closer to a prior than to a measurement.
