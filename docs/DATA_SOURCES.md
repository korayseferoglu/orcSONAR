# Data Sources and Reference Layout

Technical reference for the 24 data sources orcSONAR integrates, the on-disk
layout they are read from, the file-format conventions each one uses, and the
scoring architecture that consumes them.

- **Genome assembly:** hg38 / GRCh38 (all coordinates, without exception)
- **Cell lines:** A549, GM12878, HEK293T, HeLa, HepG2, Huh7, K562, MCF7
- **Default run:** VEGFA in HeLa

---

## 1. Directory layout

Everything under `data/` is treated as read-only reference input. It is not
tracked by git — see [Obtaining the data](#7-obtaining-the-data).

```
data/
├── 1_Temel_Harita/                    # Genomic map
│   ├── EPDnew/EPDnew_hg38.bed                 # TSS database (BED6+)
│   ├── FANTOM5/FANTOM5_hg38_CAGE_peaks.bed    # CAGE peaks (BED9)
│   └── miRBase/mature.fa                      # Mature miRNA sequences (FASTA)
├── 2_Varyant_Toksisite/               # Variant and toxicity
│   ├── COSMIC/Cosmic_GenomeScreensMutant_v103_GRCh38.vcf.gz   # + .tbi
│   └── phyloP/                                # Empty; remote BigWig is streamed
├── 3_Topoloji_Epigenetik/             # Topology and epigenetics
│   └── CCLE/CCLE_Expression.csv               # Expression matrix (~291 MB)
├── 4_Biyofizik_Yapısal/               # Biophysics and structure
│   ├── Turner_Rules/                          # 382 thermodynamic parameter files
│   ├── SHAPE_Seq/{A549,GM12878,HEK293T,HeLa,HepG2,Huh7,K562,MCF7}/
│   └── RMBase/hg38_m6A_mühürlü.bed.gz         # m6A sites, tabix-indexed
└── 5_Icra_Güvenlik/                   # Execution and safety
    ├── Immun_Motifler/immune_motifs.txt       # TLR7/TLR8 danger motifs
    ├── circAtlas/hg38_circRNAs.bed            # circRNA coordinates
    └── POSTAR3/                               # Documentation only; RBP signal
                                               # comes from remote ENCODE eCLIP
```

Directory names are Turkish and are load-bearing: they appear verbatim in
`config/config.yaml` under `data_paths`, so renaming one requires updating the
config to match.

---

## 2. Source registry

### Group 1 — Genomic map

| # | Source | Access | Location | Format | Stage |
|---|--------|--------|----------|--------|-------|
| 1 | EPDnew | Local | `data/1_Temel_Harita/EPDnew/EPDnew_hg38.bed` | BED6+ | 1 |
| 2 | FANTOM5 CAGE | Local | `data/1_Temel_Harita/FANTOM5/FANTOM5_hg38_CAGE_peaks.bed` | BED9 | 1 |
| 3 | GENCODE / Ensembl | REST API | `https://rest.ensembl.org` | JSON | 1 |
| 4 | NCBI RefSeq | REST API | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | XML/JSON | 1 |
| 5 | miRBase | Local | `data/1_Temel_Harita/miRBase/mature.fa` | FASTA | 2 |
| 6 | RepeatMasker | REST API | `https://api.genome.ucsc.edu/getData/track?genome=hg38&track=rmsk` | JSON | 2, 5 |

### Group 2 — Variant and toxicity

| # | Source | Access | Location | Format | Stage |
|---|--------|--------|----------|--------|-------|
| 7 | COSMIC v103 | Local (tabix) | `data/2_Varyant_Toksisite/COSMIC/Cosmic_GenomeScreensMutant_v103_GRCh38.vcf.gz` | VCF.gz + .tbi | 3 |
| 8 | gnomAD v4 | GraphQL API | `https://gnomad.broadinstitute.org/api` | JSON | 3 |
| 9 | NCBI ClinVar | REST API | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | XML | 3 |
| 10 | UCSC phyloP 100way | Remote BigWig | `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw` | BigWig | 3 |

### Group 3 — Topology and epigenetics

| # | Source | Access | Location | Format | Stage |
|---|--------|--------|----------|--------|-------|
| 11 | GRO-seq / PRO-seq | Remote BigWig | ENCODE, per cell line (`config/cell_lines.yaml`) | BigWig | 4 |
| 12 | ENCODE ATAC-seq | Remote BigWig | ENCODE, per cell line | BigWig | 4 |
| 13 | Hi-C (4DN) | Remote `.hic` | 4DN portal `open_data_url` (S3) | `.hic` (straw) | 4 |
| 14 | ENCODE ChIP-seq | Remote BigWig | ENCODE, per cell line (H3K4me3, H3K27ac, H3K27me3) | BigWig | 4 |
| 15 | CCLE / DepMap | Local | `data/3_Topoloji_Epigenetik/CCLE/CCLE_Expression.csv` | CSV | 4 |

### Group 4 — Biophysics and structure

| # | Source | Access | Location | Format | Stage |
|---|--------|--------|----------|--------|-------|
| 16 | Turner rules | Local | `data/4_Biyofizik_Yapısal/Turner_Rules/*.dg`, `*.dat` | Custom text | 5 |
| 17 | SHAPE-seq (icSHAPE) | Local | `data/4_Biyofizik_Yapısal/SHAPE_Seq/{cell_line}/` | Text | 5 |
| 18 | m6A-Atlas (formerly RMBase) | Local (tabix) | `data/4_Biyofizik_Yapısal/RMBase/hg38_m6A_mühürlü.bed.gz` | BED.gz + .tbi | 5 |
| 19 | ADAR editing risk | Computed | Alu proxy derived from RepeatMasker (#6) | — | 5 |
| 20 | G-quadruplex (G4) | Computed | Regex `G{3,}N{1,7}G{3,}N{1,7}G{3,}N{1,7}G{3,}` | — | 5 |

### Group 5 — Execution and safety

| # | Source | Access | Location | Format | Stage |
|---|--------|--------|----------|--------|-------|
| 21 | ENCODE Ago2 eCLIP | Remote BigWig | ENCODE, per cell line | BigWig | 6 |
| 22 | RBP competition (hnRNPA1) | Remote BigWig | ENCODE eCLIP, per cell line | BigWig | 6 |
| 23 | circAtlas 3.0 | Local | `data/5_Icra_Güvenlik/circAtlas/hg38_circRNAs.bed` | BED | 6 |
| 24 | Immune motifs | Local | `data/5_Icra_Güvenlik/Immun_Motifler/immune_motifs.txt` | Plain text | 6 |

### Access-type summary

| Type | Count | Sources |
|------|-------|---------|
| Local file | 10 | 1, 2, 5, 7, 15, 16, 17, 18, 23, 24 |
| REST / GraphQL API | 5 | 3, 4, 6, 8, 9 |
| Remote BigWig / `.hic` stream | 7 | 10, 11, 12, 13, 14, 21, 22 |
| Computed from another source | 2 | 19 (ADAR via Alu proxy), 20 (G4 via regex) |

---

## 3. Coordinate conventions

These differ between sources and are a common source of silent, off-by-one or
entirely-empty query bugs.

| Source | Chromosome naming | Note |
|--------|-------------------|------|
| COSMIC VCF | **No `chr` prefix** — `1`, `2`, `X` | Strip `chr` before querying |
| m6A BED | **Has `chr` prefix** — `chr1`, `chr2` | |
| EPDnew | **Has `chr` prefix** | |
| FANTOM5 | **Has `chr` prefix** | |
| circAtlas BED | **Has `chr` prefix** | |
| Remote BigWig (ENCODE/UCSC) | **Has `chr` prefix** | |

BED and VCF also disagree on coordinate base: BED intervals are 0-based
half-open (`[start, end)`), VCF positions are 1-based inclusive.

Hi-C queries via `hicstraw` must be **snapped to the bin boundary** of the
requested resolution; an unaligned start coordinate silently returns an empty
contact list rather than an error.

---

## 4. Format samples

### EPDnew BED — tab-separated, no header

```
chr1	959245	959305	NOC2L_1	900	-	959245	959256
chr1	960583	960643	KLHL17_1	900	+	960632	960643
```

The gene symbol is the `name` column split on `_`, first field.

### FANTOM5 CAGE BED — tab-separated, no header

```
chr1	629191	629220	hg19::chr1:564571..564600,+;hg_1.1	2972	+	629208	629209	255,0,0
```

The score column is the CAGE tag count (a proxy for expression). There are no
gene symbols, so lookup is coordinate-based only. Note that the `name` column
retains a legacy hg19 identifier; the interval itself is hg38.

### miRBase FASTA

```
>cel-let-7-5p MIMAT0000001 Caenorhabditis elegans let-7-5p
UGAGGUAGUAGGUUGUAUAGUU
```

Only `hsa-` prefixed entries are human. Sequences use `U`, not `T`.

### COSMIC VCF — tabix-indexed

```
1	65797	COSV58737189	T	C	.	.	GENE=OR4F5;TRANSCRIPT=ENST00000641515.2;STRAND=+;...;SO_TERM=SNV
```

Relevant `INFO` fields: `GENE`, `TRANSCRIPT`, `CDS`, `AA`, `SO_TERM`,
`GENOME_SCREEN_SAMPLE_COUNT`, `TIER`.

### m6A BED — tabix-indexed

```
chr1	14414	14415	m6A_site_1	0	-	m6A	2	GSE102493	GSM..	29507755	HeLa	m6A-seq	ENSG..	ENST..	WASH7P	...
```

Column 12 holds the cell line, which is how cell-specific filtering is done.

### CCLE expression — comma-separated

```
,SequencingID,ModelConditionID,ModelID,...,TSPAN6 (7105),TNMD (64102),...
0,CDS-010xbm,...,4.9565773,0.0,...
```

Gene columns are named `SYMBOL (ENTREZ_ID)`. Values are `log2(TPM + 1)`. The
file is ~291 MB, so it is read lazily rather than loaded whole.

### Immune motifs — plain text, one motif per line

```
UGUGU
GUUGUGU
UUGU
UUAU
AUAU
UUUU
```

**What a hit is measured against** (roadmap `B11c`). Four of the six motifs
are 4 nt, so chance matters: for a uniform-composition sequence of this
project's duplex length the expected hit count is **~0,5642** across both
strands, computed in closed form (`_chance_hits`), and with the
"two hits means HIGH" rule a **random** 20-mer is called `HIGH` **12,7 %** of
the time and non-`SAFE` **35,8 %** of the time (measured over 2000 random
sequences). `ImmuneResult` therefore reports `chance_hits` beside the verdict,
so the number a reader sees is not floating free. ⚠️ A
**composition-matched** null was tried and **refused by measurement**: a
mononucleotide shuffle preserves uridine content, and the motifs are largely
a U-richness detector, so the shuffled null tracks the observation almost
exactly (U fraction 0.8 → observed 8.08, shuffled null 7.99) — it cancels the
very quantity Goodchild et al. 2009 found to correlate with activity.

**Provenance, per line** (roadmap `B11c`; verified first-hand through NCBI
E-utilities, 2026-11-27). This table exists because the file itself carries
only a two-line header, so until now no line had a source — and four of the
six still do not:

| motif | primary source | note |
|---|---|---|
| `UGUGU` | Judge AD, Sood V, Shaw JR *et al.*, *Nat Biotechnol* 2005;23(4):457-62, **PMID 15778705**, DOI 10.1038/nbt1081 | ⚠️ The motif appears in the paper's **body**, not its abstract; the attribution is widely repeated in reviews and is recorded here with that limit. |
| `GUUGUGU` | **none** — it contains `UGUGU` and is GU-rich | A longer variant, not a separately published motif. Consistent with the field's GU-rich rule, but it is not an independent source. |
| `UUGU` | **none found** | U-rich 4-mer. No primary motif paper names it. |
| `UUAU` | **none found** | AU-rich 4-mer. No primary motif paper names it. |
| `AUAU` | **none found** | AU-rich 4-mer. No primary motif paper names it. |
| `UUUU` | **none found** | U-rich 4-mer. No primary motif paper names it. |

⚠️ **Two findings recorded with the table rather than silently fixed.**

1. The four unsourced entries are best read as crude proxies for
   **U/AU-richness**, and the field's own measured correlate is
   compositional rather than a set of short fixed motifs: Goodchild A,
   Nopper N, King A *et al.*, *BMC Immunol* 2009;10:40, **PMID 19630977**,
   report verbatim *"There was a significant correlation between the U count
   of the U-rich strand and the immunostimulatory activity of the duplex"*
   and *"…single-stranded, U-rich RNA species activate TLR7/8."* That is why
   `ImmuneResult` now carries `u_count` and `u_fraction` beside the motif
   hits — the correlate the literature actually measured.
2. A motif that **is** published is **missing** from the list:
   `GUCCUUCAA` (Hornung V, Guenthner-Biller M, Bourquin C *et al.*,
   *Nat Med* 2005;11(3):263-70, **PMID 15723075**, DOI 10.1038/nm1191).
   Adding it would change `data/`, which is read-only (invariant 1), so it
   is a separate decision and not made here.

⚠️ And the motif-matching model is known to be incomplete: Jurk M, Chikh G,
Schulte B *et al.*, *Nucleic Acid Ther* 2011;21(3):201-14, **PMID 21749297**,
report that *"almost all tested siRNAs with a phosphodiester backbone
actively stimulated cytokine production in human peripheral blood immune
cells, but not all of them did contain previously described"* motifs, and
identify *"a new immunostimulatory, non-uridine-rich TLR7 motif that is
present in many published siRNAs"*. So a near-universal base rate and motifs
outside any such list are both documented; the channel's categorical verdict
is reported with its measured chance rate for that reason, and §10.1 of the
pre-registration carries it as `validated: false`.

---

## 5. Pipeline stages

Each stage writes structured JSON that the next stage consumes.

1. **Genomic map** — TSS (EPDnew + FANTOM5) and transcript models
   (Ensembl/RefSeq) resolve a promoter window of −1000 / +200 bp around the TSS.
2. **Off-target scan** — seed alignment across full transcript bodies, not just
   promoter regions, plus miRBase overlap and RepeatMasker annotation. The search
   space is currently a **curated 183-gene background set**
   (`src/stage2_offtarget_scan/transcriptome_fetcher.py`); a full GENCODE
   transcriptome scan is planned.
3. **Variant and toxicity** — COSMIC, gnomAD, ClinVar, phyloP conservation.
4. **Epigenetics and topology** — ATAC-seq, histone ChIP-seq, GRO-seq, Hi-C, CCLE.
5. **Biophysics and structure** — Turner ΔG, SHAPE reactivity, m6A, ADAR, G4.
6. **Execution and safety** — Ago2 eCLIP, RBP competition, circRNA sponging,
   immune motifs.
7. **Scoring** — multi-domain integration, cell-specific modulation, risk class,
   JSON and HTML reports.

---

## 6. Scoring architecture

Implemented in `src/scoring/integrator.py`; weights and thresholds come from
`config/config.yaml`.

```
final_risk = clamp(base_score × cell_modifier, 0, 1)
```

**`base_score`** is the weighted sum of all five domain scores. The weights are
validated at runtime and must sum to exactly 1.0 (± 1e-6):

| Domain | Default weight | Inputs |
|--------|----------------|--------|
| `sequence_specificity` | 0.20 | seed match, miRNA overlap, repeats |
| `variant_toxicity` | 0.15 | COSMIC, gnomAD, ClinVar, phyloP |
| `biophysics_structure` | 0.25 | ΔG, SHAPE, m6A, ADAR, G4 |
| `epigenetic_context` | 0.20 | ATAC, ChIP, GRO-seq, Hi-C, CCLE |
| `execution_safety` | 0.20 | Ago2, RBP, circRNA, immune motifs |

**`cell_modifier`** rescales the base score by how transcriptionally active the
locus is in the chosen cell line:

```
cell_activity = 0.4 × atac + 0.4 × expression + 0.2 × execution
cell_modifier = 0.3 + 1.4 × cell_activity          # range [0.3, 1.7]
```

Missing inputs default to 0.5, so `cell_activity = 0.5` yields
`cell_modifier = 1.0` and leaves the base score untouched. A closed, unexpressed
locus shrinks the risk; an open, highly expressed one amplifies it.

**Risk classes:**

| Range | Class |
|-------|-------|
| `[0.0, 0.3)` | SAFE |
| `[0.3, 0.6)` | WARNING |
| `[0.6, 0.8)` | HIGH_RISK |
| `[0.8, 1.0]` | DANGEROUS |

### Degradation behaviour

Every data source can fail independently — a network timeout, a missing local
file, an unmapped cell line. When one does, the affected sub-score falls back to
a neutral 0.5, a warning is logged, and the pipeline continues rather than
aborting. This keeps a run completable, but it also means a report produced with
several sources unavailable is closer to a prior than to a measurement. Check the
per-stage JSON (`data_available` flags) before interpreting a score.

---

## 7. Per-cell-line coverage

Not every source exists for every supported cell line. Current state of
`config/cell_lines.yaml` and `data/`:

| Cell line | Missing sources |
|-----------|-----------------|
| A549 | Ago2 eCLIP, hnRNPA1 eCLIP |
| GM12878 | Ago2 eCLIP, hnRNPA1 eCLIP |
| HEK293T | Ago2 eCLIP, hnRNPA1 eCLIP, H3K27me3, Hi-C |
| HeLa | Ago2 eCLIP, hnRNPA1 eCLIP |
| HepG2 | — (complete) |
| Huh7 | ATAC, all histone ChIP, GRO-seq, Hi-C, Ago2 eCLIP, hnRNPA1 eCLIP |
| K562 | — (complete) |
| MCF7 | Ago2 eCLIP, hnRNPA1 eCLIP, Hi-C |

**SHAPE reactivity data is present for HeLa only** (icSHAPE, GSM4333258). The
other seven `SHAPE_Seq/` directories are empty placeholders; for those cell
lines Stage 5 reports `data_available: false` and uses the neutral fallback.

For nascent transcription, ENCODE does not offer GRO-seq or PRO-seq for every
line. `config/cell_lines.yaml` substitutes, in order of preference: PRO-seq
(A549) → PRO-cap (K562, HEK293T) → GRO-cap (GM12878) → CAGE (HeLa-S3, HepG2,
MCF-7). CAGE measures 5′ nascent TSS usage and is a proxy, not an equivalent.

---

## 8. Obtaining the data

`data/` is excluded from version control (roughly 1.5 GB) and must be assembled
locally. COSMIC in particular requires registration and a licence acceptance;
it cannot be redistributed with this repository.

Sources marked *Remote* in the registry above are streamed at run time and need
no local download — only network access. Remote reads are cached in a SQLite
database at `data/cache/orcsonar_cache.db` (default TTL: one week).
