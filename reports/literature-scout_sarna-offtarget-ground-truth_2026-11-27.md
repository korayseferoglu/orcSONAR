# saRNA (small activating RNA / RNAa) off-target ground truth — literature scout

Date: 2026-11-27. Scope: public transcriptome-wide datasets measuring off-target or
genome-wide effects of a **small activating RNA** (promoter-targeted ~21-nt duplex that
*up*-regulates transcription; RNA activation / RNAa). Self-amplifying RNA / replicon /
vaccine hits were discarded (list in §5).

Everything below was verified by fetching the record or the paper. Where a field is not in
the record or paper, it says `not stated`. No field is filled by inference.

This file is evidence, not a verdict; `AUDIT.md` and `SCIENTIFIC_ROADMAP.md` remain the
authority on what counts as a finding and what gets fixed in what order.

---

## 1. Datasets found

### 1.1 Public, downloadable, saRNA-specific

| # | Accession | Cell line | Platform | Distinct saRNA duplexes profiled | Replicates per arm | Duplex sequences published? | Non-targeting control profiled? | PMID / DOI |
|---|-----------|-----------|----------|------|------|------|------|------|
| 1 | **GSE32999** | PC-3 (prostate; **unsupported line**) | Agilent Whole Human Genome Microarray 4×44K (GPL6480) | **1** (`dsEcad-640`, E-cadherin/CDH1 promoter) — profiled alongside 5 seed-matched miRNA duplexes (miR-302a, miR-372, miR-373, miR-520c, miR-520f) | **1 array per condition**, each pooled from 4 independent transfections; mock appears on 4 arrays, miR-372 on 2 | **Yes** — Figure 1A (guide + passenger strands) and Table S3 "SiRNA sequences used in this study" | **Mock only** (transfection reagent, no duplex). No scrambled or mismatch duplex | 22205962 / 10.1371/journal.pone.0028688 |
| 2 | **GSE42024** | MCF-7 (**supported line**) | Agilent "human whole genome 4*44 chip" (GPL6480) | **1** (`dsHIC1-2998`, HIC-1 promoter). Three further duplexes (`dsHIC1-29`, `-1873`, `-2873`) were made but **not** arrayed | **3 vs 3** (GSM1030774-76 `brcell_96h_saRNA`; GSM1030777-79 `brcell_96h_control`) | **Yes** — in the Methods body: dsHIC1-2998 F `CGGUUUCCUGGAGAAGUUATT`, R `UAACUUCUCCAGGAAACCGTT` | **Unclear from paper.** A `dscontrol` duplex exists in Methods, but the paper does not state whether the array control arm was `dscontrol` or mock | 24489730 / 10.1371/journal.pone.0086486 |
| 3 | **GSE229810** | T24 (bladder; **unsupported line**) | Illumina NovaSeq 6000 (GPL24676) | **1** (`dsFOXF1-367`, FOXF1 promoter, −367 from TSS). Four candidate duplexes screened, one arrayed | **3 vs 3** (GSM7178206-08 `Negative control`; GSM7178209-11 `FOXF1-activated`) | **Yes, but supplementary-only** — Oncol Rep Table SI (not in main text; file not retrieved) | **Yes** — `dsControl`, a non-specific negative-control duplex | 37539708 / 10.3892/or.2023.8610 |

Mirrors of GSE42024: `E-GEOD-42024` (ArrayExpress), `S-ECPF-GEOD-42024` (BioStudies),
`PRJNA178940` (BioProject). GSE32999 / GSE229810 BioProject links not checked.

**Genome build:** none of the three records or papers states a build. GSE32999 and GSE42024
are 2011/2012 Agilent probe-level data (pre-hg38 probe annotations); GSE229810 is 2023
NovaSeq but the record does not name an assembly.

### 1.2 Public, but RNAa by an endogenous miRNA rather than a designed saRNA

| # | Accession | Cell line | Platform | Duplex | Replicates | Sequences | Control | PMID |
|---|-----------|-----------|----------|--------|-----------|-----------|---------|------|
| 4 | **GSE185946** (= PRJNA771412) | NCI-H1299 and H1299 DDX21-KO (**unsupported**) | Illumina HiSeq 4000 (GPL20301) | miR-34a mimic (RNAa framing) | **n=1 per arm**, 4 samples: non-treated H1299, miR-34a H1299, non-treated DDX21-KO, miR-34a DDX21-KO | miR-34a-5p is in miRBase | **No non-targeting duplex** — control is untreated | 35417682 |
| 5 | **GSE161321** (= PRJNA677880) | NCI-H1299 | Pol II ChIP-seq, 3 samples | miR-34a mimic | not stated | as above | not stated | 35417682 |

These are RNA activation, but by a natural miRNA mimic, not a promoter-designed saRNA.

### 1.3 Public, but clinical / targeted-panel rather than cell-line transcriptome

| # | Accession | Material | Platform | saRNA | Samples | Sequences | Control | PMID |
|---|-----------|----------|----------|-------|---------|-----------|---------|------|
| 6 | **GSE233860** | Paired human tumour biopsies, 24 pan-cancer patients, pre- vs on-treatment (`Screening` vs `C2D16`) | NanoString PanCancer IO gene panel (GPL27956) — targeted panel, **not** transcriptome-wide | MTL-CEBPA (CEBPA-51) **co-administered with pembrolizumab** | 48 (24 × 2 timepoints) | not in this record; CEBPA-51 sense/antisense strands with 2'-O-Me pattern are in the Methods of PMID 40686853 | No control arm — single-arm open-label phase 1 (TIMEPOINT) | 40168999 / 10.1016/j.xcrm.2025.102041 |

---

## 2. saRNA transcriptome data *claimed in a paper* but with no retrievable accession

These are **not** datasets you can download. Listed separately on purpose.

- **Voutila et al. 2012, Mol Ther Nucleic Acids 1:e35** (PMID 23344177, PMC3437803,
  doi 10.1038/mtna.2012.20) — Habib / Kasahara / Sætrom.
  Affymetrix GeneChip Human Gene 1.0 ST. Primary adult bone-marrow human MSC (not a cell
  line). **Two** duplexes profiled: `KLF4-PR1` and `MYC-PR2` (screen covered 4 KLF4 + 4
  MYC candidates). Hybridisations in **triplicate**. Control: scrambled-sequence
  oligonucleotide. **No GEO or ArrayExpress accession anywhere in the article.** Normalised
  per-replicate data are supplementary file `mtna201220x7.xls` (Table S1). Duplex
  sequences are not in the body text; Figure 1c and the supplementary Methods
  (`mtna201220x10.doc`) are the candidate locations — not confirmed.
  Design included a Hamming-distance ≥2 off-target filter; no seed-region analysis.
  *This is the largest multi-duplex saRNA expression dataset found, and it is a spreadsheet
  attached to a 2012 paper, not a repository record.*

- **bioRxiv 2025.09.29.679274** — "Small activating RNA AW1-51 (CEBPA-51) elicits targeted
  DNA demethylation to promote gene activation". RNA-seq in **K562 and A549** (both
  supported lines), **2 samples per condition**, plus **Infinium MethylationEPIC 850K**
  arrays in the same two lines, explicitly used to check off-target methylation changes.
  One duplex (`AW1-51`) plus a non-targeting `NC`. Sequences stated to be in Supplementary
  Data 1. Data availability states the RNA-seq and EPIC data "have been submitted to the
  Gene Expression Omnibus (GEO)" and that "the GEO accession number will be made publicly
  available upon journal publication" — **no accession as of 2026-11-27**.

- **Hashimoto et al. 2021, Clin Cancer Res** (PMID 34407972, PMC8756351) — MTL-CEBPA.
  RNA-seq of TAMs and PMN-MDSCs sorted from LLC tumours in **mice** treated with MTL-CEBPA
  vs NOV-FLUC control, plus NanoString PanCancer IO 360 on patient leukocytes (7 patients).
  No GEO/SRA accession in the article text; only trial IDs NCT02716012, NCT04105335.
  CEBPA-51 sequence not given in this paper.

---

## 3. Papers that *claim* saRNA specificity with no transcriptome-wide dataset at all

Relevant to the seed-mediated-analysis-of-an-saRNA question; none produced a public
genome-wide measurement.

- **Mazda et al. 2011** (PMID 22205962; the paper behind **GSE32999**) — the one paper that
  actually does a seed-mediated off-target analysis of an activating duplex. It takes the
  Li-lab E-cadherin "promoter-targeting" duplexes `dsEcad215`, `dsEcad302`, `dsEcad640` and
  argues E-cadherin induction is **seed-dependent silencing of the repressor ZEB1** via
  seed-complementary sites in the ZEB1 CDS and 3'UTR. Method: 903 transcripts carrying the
  shared `AGCACUU` 3'UTR seed match, one-sided Kolmogorov–Smirnov test of expression change
  vs non-seed-matched transcripts; 324 of the 903 commonly decreased, 114 increased;
  inter-miRNA correlation 0.62–0.86. Sylamer not used. Genome build not stated.
  **This is the exact framing orcSONAR assumes, and GSE32999 is its data.**
- **Musiała-Kierklo et al. 2025, NAR** (PMID 40829807, PMC12364543) — MBNL1 saRNA. Two lead
  duplexes. Controls include a non-targeting `saCtrl`, scrambled variants (scrA/B/C) and
  **seed-region mismatch variants MM4/MM6/MM8** (which lose RNAa activity), plus a
  luciferase reporter showing miRNA-like repression by the *sense* strand that is abolished
  by 5'-biotin. Design filtered with BLAT against **hg38**. Sequences in Supplementary
  Tables S1–S2. **No RNA-seq, no microarray, no accession.**
- **Meng et al. 2016, NAR** (PMID 26873922, PMC4797303) — "Small activating RNA binds to
  the genomic target site in a seed-region-dependent manner" (PR model). No genome-wide
  assay, no accession.
- **Portnoy et al. 2016, Cell Res** (PMID 26902284, PMC4783471) — saRNA-guided Ago2 / RITA.
  PC-3 only; all assays targeted. Duplexes `saP21`, `saEcad`, `saControl` (+ a KLF4 saRNA);
  sequences in Fig 4C–D and Supp Table S1. **No genome-wide data, no accession.**
- **DPYSL3 saRNA, Oncotarget 2016** (PMID 27014974, PMC5008410) — **22 duplexes designed**
  (8 vs DPYSL3v1 promoter, 14 vs v2), sense sequences + genomic coordinates in Table 2;
  controls = scramble saRNA, non-effective `V2-1`, mock. PC-3/C4-2/LNCaP/22RV1.
  **qPCR only — no transcriptome-wide assay, no accession.**
- **MyoAAV-saRNA utrophin, mdx mice** (PMC12636391) — 8 sequences in Table 1; mouse C2C12
  and muscle; qPCR only; no non-targeting duplex control; no accession.
- **saPtpro, Adv Sci 2026** (PMID 42517645, PMC13410807) — `saPtpro-158/-524/-525/-602`,
  sequences in Methods 4.7; mouse HT-22 and hippocampus; qPCR/western only; data "available
  from the corresponding author upon reasonable request".
- **CEBPA-51 in leukaemia, Mol Ther Nucleic Acids 2025** (PMID 40686853, PMC12271619) —
  one duplex, sequences (incl. 2'-O-Me / PS pattern) in Methods; THP-1, KG1a, MOLM-14,
  PL-21, MOLM-13 + one ex vivo AML sample; qPCR only.

---

## 4. Adjacent resource (not a transcriptome dataset)

- **saRNA curated database** — Molecules 2026, PMID 42796538, PMC13609798.
  **4,706 entries from 114 source documents, 2,424 unique saRNA sequences, 106 target
  genes**, annotated with length, GC content and modifications; coordinates mapped via an
  Ensembl retrieval workflow. Browse: `https://nic-sbi.github.io/sarna-database/`;
  data on Zenodo `10.5281/zenodo.21871232`; code `github.com/NIC-SBI/sarna-database`.
  Record does **not** list any GEO accession or off-target dataset. It is a sequence/seed
  source, not a measurement of off-target effect.

---

## 5. Explicitly excluded (self-amplifying RNA false positives)

Discarded, not counted anywhere above: GSE341822 + GSM9917894-97 (CHIKV self-amplifying
RNA + Nodamura B2, mESC); PRJNA1070838 ("Transcriptome changes in HeLa cells transfected
with self-amplifying mRNA constructs" — a HeLa transcriptome, but of a replicon, not an
saRNA); PMIDs 41826940, 41785353, 41882748, 42033816 (self-amplifying RNA therapeutics /
vector platforms); PMID 42482783 (mRNA vaccine review).

Naming trap worth recording: the **FOXF1 / GSE229810** paper's Methods heading reads
"self-amplifying RNA (saRNA)" while the experiment it describes is a promoter-targeted
activating duplex (`dsFOXF1-367`, −367 from TSS, dsControl comparator). It is RNAa; the
heading is a misnomer. It is retained in §1.

---

## 6. Can any of this support a leave-one-duplex-out evaluation?

**No.** Stated as arithmetic against what the records actually contain.

**What LODO needs.** The unit of generalisation is the *duplex*, not the sample: each
held-out duplex yields one fold and one performance estimate (AUROC, or
seed-match-vs-expression rank correlation). To put any interval on the mean across duplexes
you need enough folds for a between-duplex spread to be estimable at all — in practice
**k ≥ 10 duplexes**, each with (a) ≥3 replicates per arm, (b) a non-targeting duplex control
profiled on the *same* platform in the *same* batch, and (c) published both-strand
sequences so the seed is derivable. k = 3 gives three point estimates and a standard error
on two degrees of freedom, dominated by platform and cell-line differences between the
three series rather than by the model.

**What is actually available.**

| Requirement | Available |
|---|---|
| Distinct saRNA duplexes with a public transcriptome profile | **3** — `dsEcad-640` (GSE32999), `dsHIC1-2998` (GSE42024), `dsFOXF1-367` (GSE229810) |
| …with ≥3 replicates per arm | **2** (GSE42024, GSE229810). GSE32999 is 1 pooled array for the saRNA arm |
| …with a non-targeting duplex control, not mock | **1 confirmed** (GSE229810 `dsControl`). GSE42024 unclear; GSE32999 mock only |
| …with both-strand sequences published | **2 confirmed in-text** (GSE42024, GSE32999). GSE229810 supplementary Table SI, not retrieved |
| Distinct cell lines | 3 — PC-3, MCF-7, T24. Only **MCF-7** is in `config/cell_lines.yaml` |
| Distinct platforms | 2 technologies (2× Agilent 4×44K, 1× NovaSeq RNA-seq); no duplex pair shares a platform *and* a cell line |
| Duplexes targeting the same gene | **0** — HIC-1, CDH1, FOXF1, one duplex each |

Pooling cannot fix this: every fold would differ in cell line **and** platform
simultaneously, so a per-duplex performance difference is not attributable to the duplex.

**If the two off-repository sources were brought in** (Voutila Supplementary Table S1,
2 duplexes in primary hMSC on Affymetrix Gene 1.0 ST; and the AW1-51 preprint's K562/A549
RNA-seq once its accession appears), the pooled count rises to **5–6 duplexes across 4
platforms and 5 biological materials**. Still short of k ≥ 10, and two are not from a
repository.

**The one dataset matching the project's exact assumption** is GSE32999: the only public
record where an activating duplex's transcriptome-wide effect is analysed *as* a
seed-mediated off-target effect, with 5 miRNA duplexes sharing the same seed as internal
comparators. Its weaknesses are n=1 array for the saRNA arm and a mock rather than
scrambled control.

---

## 7. Verdict

```
SARNA GROUND TRUTH EXISTS (GSE42024, GSE229810, GSE32999; pooled n=3 duplexes)
```

Not "only GSE42024" — GSE32999 and GSE229810 are real, public, saRNA-specific and were not
previously known to the project. But n=3 duplexes across 3 cell lines and 2 platforms, with
one arm unreplicated, does not support a leave-one-duplex-out evaluation of seed-mediated
off-target prediction. The external-validity gap narrows from 1 duplex to 3; it does not
close.

---

## 8. Queries run (reproducible)

GEO (E-utilities `db=gds`, then `esummary` on returned UIDs):
1. `"small activating RNA" OR "RNA activation" OR saRNA OR RNAa` → 71 UIDs
2. `"antigene" OR "agRNA" OR "promoter-targeted"` → 59 UIDs
3. `(saRNA[All Fields] OR "small activating"[All Fields]) AND "Homo sapiens"[orgn]` → 16
4. `(("activating RNA") OR (saRNA) OR (RNAa) OR (agRNA) OR (antigene)) AND gse[Entry Type] AND "Homo sapiens"[Organism]` → 14
5. `(CEBPA OR CDKN2B OR p21 OR CDH1 OR VEGFA OR KLF4 OR NKX3-1 OR PCBP1) AND (saRNA OR "small activating" OR "RNA activation")` → 3
6. `("dsRNA" AND "promoter" AND ("upregulation" OR "activation")) AND gse[entry type]` → 10
7. `("duplex RNA" OR "double-stranded RNA") AND promoter AND (upregulat* OR activat*) AND gse[Entry Type] AND "Homo sapiens"[Organism]` → **0**
8. `"dsP21" OR "saP21" OR "dsEcad" OR "saEcad" OR "dsVEGF" OR "dsControl" OR "saControl" OR "dsHIC1" OR "dsFOXF1"` → 11 (**surfaced GSE32999**)
9. `"dsEcad215" OR "dsEcad302" OR "dsEcad640" OR "dsEcad" OR Ui-Tei[Author] OR Mazda[Author]` → 12
10. `"RNAa"[All Fields] AND gse[Entry Type]` → 5
11. `MBNL1 AND (duplex OR saRNA OR "small RNA" OR promoter)` → 21
12. `"Corey DR"[Author] AND gse[Entry Type]` → 14 (all AGO/TNRC6/miRNA; no agRNA series)
13. `("Li LC"[Author] OR "Place RF"[Author] OR "Habib NA"[Author] OR Reebye[Author] OR Voutila[Author]) AND gse[Entry Type]` → 19 (**surfaced GSE233860**)
14. `(Corey[Author] OR Janowski[Author]) AND gse[Entry Type]` → 261 (too broad, abandoned)
15. `"MTL-CEBPA" OR "CEBPA-51" OR "AW1-51" OR "saRNA-CEBPA" OR "CEBPA saRNA"` → 96 (tokenised to CEBPA; abandoned)

Other repositories:
16. SRA: `"small activating RNA" OR "RNA activation"` → **0**
17. BioProject: `("small activating RNA" OR "RNA activation" OR "saRNA") AND "Homo sapiens"[Organism]` → 6 (PRJNA178940 = GSE42024; PRJNA771412/677880 = miR-34a; PRJNA1070838 = self-amplifying, excluded)
18. BioStudies/ArrayExpress: `"small activating RNA"` → 31 studies; only `E-GEOD-42024` / `S-ECPF-GEOD-42024` are array records. **No E-MTAB saRNA entry.**

PubMed / Europe PMC:
19. PubMed: `("small activating RNA" OR "RNA activation"[ti] OR "saRNA") AND (microarray OR "RNA-seq" OR transcriptome OR "gene expression profil*") AND ("off-target" OR specificity)` → 13 (**surfaced Voutila 2012**)
20. EPMC: `("small activating RNA" OR "RNA activation" OR saRNA) AND ("off-target" OR microarray OR "RNA-seq" OR transcriptome) AND (GEO OR GSE)` → 50
21. EPMC: `("small activating RNA" OR "RNA activation" OR "saRNA") AND ACCESSION_TYPE:"geo"` → 87, of which exactly **2** are saRNA primary studies (24489730, 42168992)
22. EPMC: `("small activating RNA" OR "short activating RNA" OR "antigene RNA" OR "agRNA") AND ("Gene Expression Omnibus" OR ArrayExpress OR "Sequence Read Archive")` → 38
23. EPMC: `"RNA activation" AND "small activating RNA" AND ("genome-wide" OR "transcriptome-wide" OR "microarray analysis")` → 18
24. EPMC: `("small activating RNA" OR saRNA) AND microarray AND promoter AND HAS_SUPPL:y` → 27
25. EPMC: `"RITA complex" OR "saRNA-guided" OR (AUTH:"Portnoy V" AND "Ago2")` → 51 (**surfaced the curated saRNA database, PMID 42796538**)
26. EPMC: `"Small activating RNA AW1-51" OR "CEBPA-51"` → 29
27. EPMC core-record fetches on PMIDs 37539708, 23344177, 23929703, 40829807, 42168992, 37234746, 22205962, 26873922

Full texts read: PMC3437803 (Voutila), PMC12364543 (MBNL1), PMC3244408 (Mazda/GSE32999),
PMC3904905 (HIC-1/GSE42024), PMC4783471 (Portnoy), PMC8756351 (Hashimoto), PMC12271619
(CEBPA leukaemia), PMC13410807 (saPtpro), PMC12636391 (utrophin), PMC5008410 (DPYSL3),
PMC13377778 (PCBP1), PMC13609798 (saRNA database),
spandidos-publications.com/10.3892/or.2023.8610 (FOXF1/GSE229810),
biorxiv.org/content/10.1101/2025.09.29.679274v1.full (AW1-51).

Note: `ncbi.nlm.nih.gov/geo/query/acc.cgi` returned a browser-verification page throughout;
all GEO record detail above came from E-utilities `esummary` (`db=gds`, `version=2.0`).

---

`6 datasets found across 27 queries` (3 saRNA-specific and public: GSE32999, GSE42024,
GSE229810; 1 clinical panel: GSE233860; 2 miRNA-RNAa: GSE185946, GSE161321)
