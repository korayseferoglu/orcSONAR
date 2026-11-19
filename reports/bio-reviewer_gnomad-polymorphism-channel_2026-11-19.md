# bio-reviewer — gnomAD polymorphism channel (post-B4)

Date: 2026-11-19
Scope: `src/stage3_variant_tox/gnomad_client.py`, `src/stage3_variant_tox/variant_merger.py`,
and the coordinate path feeding them.
Status: evidence, not verdict. `AUDIT.md` and `SCIENTIFIC_ROADMAP.md` remain authority.

---

## 1. What the code actually computes

**The description in the task brief is CONFIRMED in every particular.**

| Claim | Verdict | Evidence |
|---|---|---|
| Producer docstring says "no common variants → conserved → score = 1.0" | confirmed | `gnomad_client.py:264-269` |
| Empty case: "no data → assume conserved → high risk" | confirmed | `gnomad_client.py:277-278` |
| Field named `polymorphism_score`, value is already a risk score | confirmed | `gnomad_client.py:261-280`, `models.py:234` |
| Consumer previously did `1.0 - score`; B4 removed the inversion | confirmed | `variant_merger.py:36-45` (comment + current line 45) |

Mechanics, precisely:

- **"Common variant" cutoff:** `_AF_COMMON_THRESHOLD = 0.01` (`gnomad_client.py:26`). This is
  the standard MAF ≥ 1% definition and is defensible *as a cutoff*. But it is not used as a
  cutoff — see the transfer function below.
- **Transfer function:** `score = max(0.0, 1.0 - max_af / 0.01)` (`gnomad_client.py:280`),
  over `max_af = max(v.allele_frequency for v in variants)` (`gnomad_client.py:146`, `279`).
- **AF per variant:** `max(genome_af, exome_af)`, nulls coerced to 0.0, clamped to [0,1]
  (`gnomad_client.py:240-246`).
- **Window:** the stage-2 off-target region, passed straight through — `site["region"]` read
  verbatim in `site_keys.py:49`, no re-derivation in stage 3. In the reference runs that is a
  20-nt window (`results/VEGFA_HeLa/stage3_gnomad.json:4-9`: `chr1:11255438-11255458`),
  i.e. the full saRNA:mRNA footprint, built as `win_end = win_start + sarna_len`
  (`seed_aligner.py:83`).
- **Empty/no-data:** `1.0` (`gnomad_client.py:278`). **API failure:** `0.5`
  (`gnomad_client.py:124-130`). **Missing site in the merger:** `1.0`
  (`variant_merger.py:45`). Three different numbers for three flavours of "we don't know",
  none of them `null`.
- **Weight:** `0.20 * gnomad_risk` of the stage-3 score (`variant_merger.py:53`), and
  `variant_toxicity` is 0.15 of `base_score` — so this channel owns **0.03 of the final risk**.

Observed behaviour, from the reference run: the MTOR site
`results/VEGFA_HeLa/stage3_gnomad.json:3-71` has 8 variants, `max_af = 0.00685`, and
`polymorphism_score = 0.3154`. A single allele at **0.68 %** frequency moved that site 68 %
of the way to "safe". 0.68 % is not a common variant by any population-genetics convention;
~1.4 % of individuals carry one copy.

---

## 2. Findings

### F1 — the gnomAD window is a median 30,732 bp away from the off-target site (CONFIRMED)

```
src/stage2_offtarget_scan/seed_aligner.py:105-111  (origin)
src/stage3_variant_tox/gnomad_client.py:193        (consumer)
```

WHAT: the interval handed to gnomAD is a cDNA offset added to a transcript start as if the
transcript were unspliced, so it names a locus that is usually intronic and is not the
off-target site.
WHY: cDNA→genomic conversion must walk exon blocks; `g_start = t_info.start + win_start`
assumes a single exon. Measured in `.claude/rules/10-koordinatlar.md` and `AUDIT.md:437-443`:
median deviation 30,732 bp, 39/41 sites >1 kb.
EFFECT: every `polymorphism_score` in `results/` is a population-genetics measurement of a
near-random intronic 20-mer. B4 corrected the *sign* of a number whose *locus* is wrong. No
conclusion about the gnomAD channel's calibration, distribution or ceiling can be drawn from
the existing runs. (Roadmap `D2`; listed here because it dominates every other finding below.)

Note the stage-2→stage-3 boundary itself is **sound**: `site_keys.py:49` passes the region
through rather than re-deriving it. The error is upstream of the boundary, not at it.

### F2 — `GenomicRegion` has no declared coordinate base and the three stage-3 clients read it three different ways (CONFIRMED)

```
src/core/models.py:10-28                     (no base declared; length = end - start)
src/stage2_offtarget_scan/transcriptome_fetcher.py:266-267 (producer: Ensembl, 1-based inclusive)
src/stage3_variant_tox/gnomad_client.py:211-222            (consumer: needs 1-based inclusive)
src/stage3_variant_tox/cosmic_scanner.py:93                (consumer: pysam, 0-based half-open)
src/stage3_variant_tox/phylop_scorer.py:126-136            (consumer: pyBigWig, documented 0-based exclusive)
```

WHAT: one field carries one number that four modules interpret under three incompatible
conventions; at most one of them is reading the right bases.
WHY: Ensembl REST returns 1-based inclusive coordinates, so `t_info.start + win_start`
(`seed_aligner.py:107`) is a 1-based position. `pysam.TabixFile.fetch` and `pyBigWig.stats`
are both 0-based half-open. gnomAD GraphQL `region(start:, stop:)` is 1-based inclusive.
EFFECT: COSMIC and phyloP queries are shifted one base relative to the window gnomAD queries.
On a 20-nt footprint that is a 5 % disagreement about which bases the four stage-3 channels
are scoring — they do not describe the same interval.

### F3 — `region.end` is exclusive but is passed as gnomAD's inclusive `stop` (CONFIRMED)

```
src/stage3_variant_tox/gnomad_client.py:193, 211-222
```

WHAT: the query covers one base more than the saRNA footprint — the base immediately after
the duplex.
WHY: `end` is exclusive (`models.py:28` `length = end - start`; `seed_aligner.py:83`
`win_end = win_start + sarna_len`), while GraphQL `stop` is inclusive. Correct arithmetic is
`stop: end - 1` for a half-open `end`, or `start + 1` if `start` is treated as 0-based. The
docstring at `gnomad_client.py:217-219` states "0-based start position" and then passes it
unconverted, so the mismatch is documented and not acted on.
EFFECT: one extra base in 21 (~5 % window inflation), and the extra base is outside the duplex
— it can only *add* variants, so it can only *raise* `max_af`, which post-B4 can only
*lower* the risk score. Small, but systematically anti-conservative.

### F4 — a single `max_af` over 20 bp is not an estimator of constraint (CONFIRMED, modelling)

```
src/stage3_variant_tox/gnomad_client.py:261-280
```

WHAT: the channel infers "this site is evolutionarily unconstrained" from whether one allele
in a 20-bp window reached ~1 % frequency.
WHY: whether a given 20-bp window segregates a ≥1 % allele is dominated by (i) local mutation
rate, which varies >10-fold across the genome by sequence context, (ii) gnomAD ascertainment —
exome capture vs genome cohort, coverage depth, callability filters, and (iii) the variance of
the site frequency spectrum, under which a neutral allele's frequency is a high-variance single
draw. Purifying selection is the *fourth* term and is not detectable at 20-bp scale without an
expected-vs-observed mutation model. This is precisely why gnomAD publishes constraint at gene
scale (LOEUF, pLI, aggregating hundreds of variants) and at 1-kb scale for non-coding
(Gnocchi), with explicit mutation-rate expectations. The code builds none of that: no expected
counts, no mutation-rate model, no coverage normalisation.
EFFECT: the per-site number is noise with a constraint-shaped name. The downstream risk model
treats it as a 0.20-weighted measurement.

### F5 — the transfer function is maximally sensitive exactly where AF is least informative (CONFIRMED)

```
src/stage3_variant_tox/gnomad_client.py:280
```

WHAT: `1 - max_af/0.01` ramps from 1.0 to 0.0 over AF ∈ [0, 0.01] and is flat at 0.0 for all
AF ≥ 0.01.
WHY: AF 1 % and AF 50 % score identically, but they are not remotely the same statement —
about constraint *or* about any individual genome. Meanwhile AF 0.1 % vs 0.5 % (both rare, both
nearly uninformative, both plausibly a single-family allele) swing the score by 0.4.
EFFECT: the channel's dynamic range is spent on the frequency band that carries the least
information, and is saturated across the band that carries the most. Empirically this makes the
distribution near-bimodal — 7/41 sites pinned at 0.0 per `SCIENTIFIC_ROADMAP.md:175` and the
rest clustered near 1.0.

### F6 — `ref`/`alt` are parsed and then never used, so the binding-axis sign is undetermined per site (CONFIRMED)

```
src/stage3_variant_tox/gnomad_client.py:261-280 (score ignores alleles)
src/core/models.py:222-223                      (ref/alt are carried, unused)
```

WHAT: the score assumes every variant *destroys* the guide match. A variant whose **alt allele
is the one complementary to the guide** *creates* an off-target site that does not exist in the
reference — and gets scored as risk-reducing.
WHY: off-targets are called against the reference sequence (`seed_aligner.py:88-89`). A SNP can
break a reference match or create a non-reference match; the direction depends on which allele
pairs with the guide. The data needed to tell them apart is sitting in `GnomadVariant.ref` /
`.alt` and is never read.
EFFECT: for an unknown fraction of sites the channel points the wrong way, and nothing in the
code or the output distinguishes those sites.

### F7 — "no gnomAD data → conserved" is a callability artifact, not a biological inference (CONFIRMED)

```
src/stage3_variant_tox/gnomad_client.py:277-278
```

WHAT: an empty variant list is read as "this window is conserved" and emitted as a measured
1.0 at full weight.
WHY: gnomAD returns nothing at a locus for reasons that are overwhelmingly technical, and those
reasons are systematic by region class:
- **segmental duplications and low-mappability regions** — short-read callsets are depleted
  there and gnomAD hard-filters/flags them;
- **low-complexity regions, STRs, satellite, pericentromeric and acrocentric sequence, rDNA** —
  effectively uncallable;
- **anything outside exome capture** is backed only by the ~76k-genome cohort, roughly an order
  of magnitude less AF resolution than the ~730k exomes; intronic and intergenic windows live
  here;
- **GC-extreme first exons and CpG-rich promoter-proximal sequence**, which fail coverage
  thresholds more often than average — and which is exactly the sequence class an saRNA
  promoter-targeting tool cares about.

Are those classes enriched or depleted among *this* pipeline's off-target sites? **Enriched**,
twice over. Off-target seed hits are short degenerate motifs and land in repeats more often than
chance — the pipeline runs RepeatMasker at stage 2 for exactly that reason. And F1 pushes the
queried windows into introns, where Alu/L1 density approaches 50 %.

So "empty → 1.0" maps *unmappable repetitive sequence* onto *maximum constraint risk*. That is
backwards about the biology: repeats and segdups are among the least constrained sequence in the
genome, and the reason gnomAD is silent there is that the assay cannot see them, not that
selection removed the variants.

The empirical density settles it: the reference runs show **8 variants per 20-bp window**
(`AUDIT.md:574-577`; `results/VEGFA_HeLa/stage3_gnomad.json:68`). At that density a genuinely
callable 20-mer returning zero is rare. In practice an empty list means *not callable*, not
*ultraconserved* — and the code cannot tell the difference because it never queries gnomAD's
`coverage` field, which exists for precisely this.

EFFECT: the most repetitive, least constrained, least mappable off-target sites receive the
channel's maximum risk value, as a *number* rather than an *unknown*.

**On fail direction:** the fail-dangerous policy is not in dispute and is not what this finding
objects to. The objection is that the B2-consistent way to be fail-dangerous is `null` +
weight renormalisation, so the risk model knows the locus was *not examined*; minting a 1.0
asserts a measurement that was not made and lets it average with real measurements.

### F8 — three un-migrated B2 fallbacks in one channel, with contradictory values (CONFIRMED)

```
src/stage3_variant_tox/gnomad_client.py:124-130   (API failure → 0.5, a numeric risk value)
src/stage3_variant_tox/gnomad_client.py:278       (empty → 1.0)
src/stage3_variant_tox/variant_merger.py:45       (missing site → 1.0)
src/stage3_variant_tox/gnomad_client.py:323-324   (run()-level failure → every site gets 1.0)
```

WHAT: `_query_gnomad_region` returns `polymorphism_score = 0.5` on an exception — a numeric risk
value produced by a failure path, in score space.
WHY: B2's acceptance criterion is "no fallback path returns a numeric risk value"
(`SCIENTIFIC_ROADMAP.md:174`). `variant_merger` was not among the two mergers B2 migrated; it
has no unknown handling at all (`_NEUTRAL = 0.5` at `variant_merger.py:12` is defined and never
used).
EFFECT: an API outage is indistinguishable in the output from a measured mid-polymorphism site;
a whole-run outage gives all sites an identical 1.0, which is a constant offset carrying zero
information while occupying 0.20 of the stage-3 weight.

Secondary, same function: `variant_merger.py:34` defaults a missing COSMIC channel to `0.0` and
`:46-48` defaults missing ClinVar to `0.0` — the **safe** end — while gnomAD defaults to the
risky end. Within one `_normalize` call, three of four channels fail safe and one fails
dangerous. That is an internal inconsistency in how the merged number should be read, whatever
the intended policy is.

### F9 — `max(genome_af, exome_af)` instead of the joint AF (CONFIRMED, small)

```
src/stage3_variant_tox/gnomad_client.py:244
```

WHAT: taking the maximum of two overlapping cohort frequencies rather than the pooled estimate.
WHY: gnomAD v4 publishes a joint AF precisely so consumers do not do this. For an allele seen
once in each cohort, `max` picks the smaller-denominator (noisier, larger) estimate — ~1.3e-5
from 76k genomes rather than ~2.5e-6 pooled.
EFFECT: `max_af` is biased upward, which post-B4 biases the risk score downward. Always in the
anti-conservative direction. Magnitude is small at the 1 % scale but it is a one-way bias.

### F10 — AF-null variants become AF 0.0 and are then indistinguishable from "conserved" (CONFIRMED, small)

```
src/stage3_variant_tox/gnomad_client.py:242-243
```

WHAT: a variant whose AF is unreported is scored as frequency zero, i.e. maximally rare.
EFFECT: a window of eight AF-null calls scores 1.0 — the same as an empty window — while
`variant_count = 8` in the output makes it look measured. Fail-dangerous, so low priority, but
it means `variant_count` and `polymorphism_score` can disagree about whether anything was seen.

### F11 — a second, inconsistent gnomAD transfer function in the dead scoring module (NOTED)

```
src/scoring/domain_scores.py:127-128  →  gnomad_reduction = gnomad.max_af * 0.30
```

Same *direction* as post-B4 (high AF reduces risk, so B4 did not create a contradiction here),
but a different function: linear in raw AF across [0,1] with no 1 % threshold, applied as a
subtraction rather than a weighted term. Per `.claude/rules/20-skor-degismezleri.md` this module
has zero production callers and 44 of 91 tests in the largest test file target it, and `B8`
plans to port its "behavioural intent" into production. If that port happens unexamined, it
ports a *third* gnomAD transfer function into the live path.

---

## 3. The core question: is "polymorphic → lower off-target risk" sound?

Answer in three parts, because the question contains two different claims and the code conflates
them.

### 3a. Which claim does the score actually measure?

The producer's docstring commits to the **consequence** claim: "the saRNA is less likely to
disrupt conserved function" (`gnomad_client.py:5-6`), "highly polymorphic sites are functionally
less critical" (`domain_scores.py:104`). That is a statement about *tolerance to perturbation*.

The quantity computed — "is there a ≥1 % allele in this 20-bp window" — is a weak, high-variance
proxy for that, for the reasons in F4. But it is a *direct* statement about something else: **the
probability that an arbitrary human chromosome spells this site differently from the reference**.
That is the **binding** claim.

So the code measures (noisily) the binding quantity and labels it with the consequence quantity.
These are different claims, they need different data, and the risk model needs the consequence
one — because the off-target harm an saRNA causes is *dosage* harm to a bystander gene, not
sequence harm to a base.

### 3b. Direction on each axis — both point the same way, so B4 did not pick the wrong sign

**Binding axis.** An saRNA guide binds by Watson–Crick complementarity, seed-dominated. A
variant inside the duplex footprint:
- in guide positions 2–8, a single mismatch generally abolishes AGO-mediated recognition;
- in the 3' region, a mismatch is largely tolerated.

A ≥1 % allele that breaks the seed does reduce expected off-target binding **in carriers**. So:
polymorphic → slightly less binding → slightly lower risk. **Direction: down.** Correct sign.

But the *magnitude* is wrong by two orders of magnitude. The expected fraction of chromosomes
that still match the guide is exactly `1 - AF`. At AF = 0.01 the correct binding-risk multiplier
is **0.99**. The code applies **0.00**. A proper binding-axis model would be a `(1 - AF)` allele-
dosage multiplier, restricted to variants that fall in positions 2–8 *and* whose alt allele
breaks complementarity (F6), not a step function that zeroes the channel at the 1 % mark.

There is no positional weighting at all: `max` is taken over the whole 20-nt footprint
(`gnomad_client.py:279`), so a SNP at guide position 19 counts the same as one at position 3.

**Consequence axis.** Granting the constraint inference for argument's sake: polymorphic →
tolerant to perturbation → an off-target hit there matters less. **Direction: also down.**

So **B4's direction is the defensible one of the two available signs.** Both readings agree.
The previous session's self-criticism — "I aligned the sign, I did not question the model" — is
well placed, but the answer is that the sign it chose is not the problem.

### 3c. Where it breaks anyway — the category error

Tolerance to a **single-nucleotide substitution in DNA** is not tolerance to **altered transcript
abundance**. A common synonymous or 3'UTR SNP tells you one base change is survivable; it tells
you nothing about whether halving or doubling that transcript is survivable. saRNA off-target
harm is dosage harm. The gnomAD-derived quantity that actually speaks to dosage tolerance is
**gene-level**: LOEUF / pLI for loss, and triplosensitivity (pTriplo) for gain — which is the
relevant direction for an *activating* RNA.

This matters operationally: gene-level metrics are **gene-keyed**, and gene identity is the one
thing F1 does *not* corrupt — `.claude/rules/10-koordinatlar.md` states explicitly that "which
gene took the hit" is unaffected by the splice-blindness bug, and `site_id` field 0 carries it
(`.claude/rules/20-skor-degismezleri.md`). A LOEUF/pTriplo channel would be immune to D2, would
be a static table rather than a 1 Hz API, and would measure the thing the docstring claims to
measure.

### 3d. Cell lines: does a population frequency mean anything about HeLa?

**No.** A population AF is a prior over randomly sampled human chromosomes. The pipeline's
subjects are not that:

- They are **cancer lines** carrying somatic mutations that are, by construction, absent from
  gnomAD — gnomAD is a germline resource and filters somatic-looking calls. A cell-line-private
  or somatic allele that breaks the seed scores AF ≈ 0 → `polymorphism_score` 1.0 → **maximum**
  risk, for a site that does not exist in that line. That is exactly backwards, and it is the
  case the channel most needs to get right.
- They are **aneuploid with extensive CNV and LOH**: HeLa is near-triploid with HPV-18
  integration; K562 is near-triploid with BCR-ABL amplification; HepG2 carries broad LOH. Copy
  number changes the target dosage at an off-target locus, and population AF says nothing about
  it.
- Conversely a site the line carries as **reference** has its risk discounted by a 1 % allele
  the line does not carry at all. In the reference run, the MTOR site is discounted 68 % by a
  0.68 % allele (`results/VEGFA_HeLa/stage3_gnomad.json:69-70`) — the probability HeLa carries
  it is ~1.4 %.

**Defensible alternatives**, in increasing cost:

1. **Report-only.** Keep `max_af` as an annotation (it is already surfaced at
   `variant_merger.py:118`) and remove the AF-derived term from the merged score. Costs nothing
   and stops the channel from asserting a number it cannot support.
2. **Gene-level dosage constraint** (gnomAD LOEUF / pLI, pHaplo / pTriplo) in place of the
   per-site AF term. Same vendor, gene-keyed, D2-immune, static table, no rate limit. This is
   the one that measures what the docstring claims.
3. **The cell line's own genotype**, for the binding axis. DepMap publishes per-line somatic
   variant calls and gene-level copy number; `config/ccle_depmap_ids.yaml` already maps ACH IDs
   and `config/config.yaml:73` already wires one DepMap CSV (expression only — no genotype
   source is currently configured). GM12878 is NA12878, a fully phased GIAB benchmark genome —
   its genotype is exactly known. **Coverage is not uniform:** `config/ccle_depmap_ids.yaml:13`
   already records that HEK293T is absent from CCLE, and `config/cell_lines.yaml:29-30` records
   that Huh7 has no ENCODE coverage at all. So this cannot be applied to all eight supported
   lines and must produce an explicit per-line `null`, not a default — a line silently falling
   back to the population prior would be the same class of bug this channel already has.

   Done properly, option 3 should edit the **site list**, not nudge a weight: if the line is
   homozygous for a seed-breaking allele, the off-target site does not exist in that line and
   should be removed, not scored 0.0.

---

## 4. Verdict

**The post-B4 direction is right. The channel is not interpretable as a per-site risk score in
either direction.**

Those are separate statements and both hold:

- B4 is **correct and should stand**. The producer's contract is unambiguous, the consumer did
  contradict it, and the sign B4 settled on is the one both the binding reading and the
  consequence reading agree on. Reverting it would be wrong.
- The channel is nonetheless **not measuring something that belongs in the score as implemented**.
  Ranked by how badly each breaks it:
  1. the queried locus is a median 30 kb from the site (F1) — until `D2`, every value is a
     measurement of the wrong place;
  2. a single `max_af` over 20 bp is not an estimator of constraint (F4), and the transfer
     function spends its whole dynamic range below the 1 % mark where AF is least informative
     (F5);
  3. per-site sign is undetermined because `ref`/`alt` are never consulted (F6);
  4. a population prior is applied to aneuploid cancer genomes whose relevant alleles are
     somatic and therefore invisible to gnomAD (3d);
  5. "no data" is minted as a measured 1.0 rather than an unknown, and the region classes that
     produce no data are exactly the repetitive, unmappable, *least* constrained ones, which are
     *enriched* among this pipeline's off-target sites (F7).

Recommended framing for the roadmap (not a fix, a judgement): this channel is currently
**annotation, not evidence**. It carries 0.03 of final risk, so it is not the most urgent repair
— but it should stop being described as a population-genetics-informed risk term, because the
quantity it computes does not support that description at 20-bp resolution, and the one gnomAD
quantity that would (gene-level dosage constraint) is cheaper to obtain and immune to the
coordinate bug that invalidates everything else in stage 3.

---

## 5. Coverage — boundaries checked and found sound

So the caller knows where I looked and found nothing to report:

- **chr-prefix at the gnomAD boundary** — `gnomad_client.py:192` strips `chr` before the query,
  correct per the source registry (gnomAD uses bare `1`, `X`), and the cache key
  (`gnomad_client.py:112`) consistently retains the prefixed form. Sound.
- **Build** — `reference_genome: GRCh38` is hardcoded in the query template
  (`gnomad_client.py:44`) and `dataset: gnomad_r4` is correctly placed on the inner
  `variants(...)` field, both unquoted as enums. No GRCh37 default anywhere in this path. Sound.
- **Stage 2 → stage 3 region hand-off** — `site_keys.py:44-54` passes `site["region"]` through
  verbatim and keeps ids index-aligned; no re-derivation, which is the failure shape I was asked
  to hunt. Sound at the boundary (the value arriving is wrong for reasons upstream — F1).
- **Strand in the gnomAD query** — ignored, which is correct: population variants are
  strand-agnostic genomic facts and gnomAD reports alleles on the plus strand. Latent trap only:
  `ref`/`alt` are stored without strand normalisation (`gnomad_client.py:249-253`), so if F6 is
  ever addressed by comparing alleles to the guide, a minus-strand site will need
  reverse-complementing.
- **Units and ranges** — AF is dimensionless and clamped to [0,1] (`gnomad_client.py:246`);
  `polymorphism_score` is bounded [0,1] by construction (`gnomad_client.py:280`) and by the model
  field (`models.py:234`). No unnormalised raw signal enters the risk model from this channel.
  Sound.
- **Seed convention** — not exercised in this path; `gnomad_client` never slices the guide.
