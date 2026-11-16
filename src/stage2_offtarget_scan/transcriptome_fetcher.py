"""Background human transcriptome fetcher for whole-transcriptome off-target scanning.

Fetches canonical mRNA sequences for a curated set of highly-expressed human
protein-coding genes via Ensembl REST API, with SQLite caching (TTL 1 week).

On first run this issues ~5-10 POST requests to Ensembl and caches every result.
Subsequent runs load everything from SQLite (< 1 second).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import TranscriptInfo

_ENSEMBL_DELAY = 1 / 15        # 15 req/s
_LOOKUP_BATCH = 80              # genes per POST /lookup/symbol (smaller batch avoids 60s+ Ensembl response times)
_SEQ_BATCH = 50                 # transcript IDs per POST /sequence/id

# ---------------------------------------------------------------------------
# Curated gene list (broad expression across human cell lines)
# Selection: housekeeping + RNA-biology + cancer-relevant + RISC pathway
# ---------------------------------------------------------------------------

_BACKGROUND_GENES: tuple[str, ...] = (
    # Housekeeping / ribosomal
    "ACTB", "GAPDH", "HSPA8", "HSP90AA1", "HSP90AB1",
    "RPL5", "RPL6", "RPL7", "RPL10", "RPL11", "RPL13", "RPL14", "RPL18",
    "RPS3", "RPS5", "RPS6", "RPS8", "RPS11", "RPS13", "RPS14",
    "EEF1A1", "EEF2", "EIF4A1", "EIF4B", "EIF4E",
    "UBB", "UBC", "UBA52",
    "TUBB", "TUBA1A", "TUBA1B",
    "VIM", "LMNA",
    # hnRNP / RNA-binding proteins
    "HNRNPA1", "HNRNPA2B1", "HNRNPC", "HNRNPD", "HNRNPK", "HNRNPL", "HNRNPM",
    "PTBP1", "PTBP2",
    # RISC / RNA-silencing pathway
    "AGO1", "AGO2", "AGO3", "AGO4",
    "DICER1", "DROSHA", "DGCR8",
    "TARBP2",
    "TNRC6A", "TNRC6B", "TNRC6C",
    "MOV10", "DDX5", "DDX17",
    # Cell cycle / replication
    "PCNA", "MCM2", "MCM3", "MCM4", "MCM5", "MCM6",
    "CDK4", "CDK6", "CCND1", "CCND2", "CCNE1",
    "CCNA2", "CCNB1", "CDC20", "PLK1", "AURKA", "AURKB",
    # Oncogenes & tumor suppressors
    "TP53", "MDM2",
    "MYC", "MYCN", "MAX",
    "KRAS", "NRAS", "HRAS", "BRAF",
    "EGFR", "ERBB2", "ERBB3",
    "PIK3CA", "PIK3CB",
    "AKT1", "AKT2",
    "PTEN", "RB1", "CDKN2A",
    "VEGFA", "VEGFB", "VEGFC",
    "MET", "HGF",
    "JAK1", "JAK2", "STAT3",
    "BCL2", "BCL2L1", "MCL1", "BAX",
    "BRCA1", "BRCA2",
    "ATM", "ATR", "CHEK1", "CHEK2",
    # Epigenetics
    "EZH2", "HDAC1", "HDAC2", "DNMT1",
    # Signaling cascades
    "MAPK1", "MAPK3", "MAP2K1",
    "MTOR", "TSC1",
    "CTNNB1", "APC",
    "NOTCH1", "HES1",
    "TGFB1", "SMAD2", "SMAD3", "SMAD4",
    "HIF1A",
    "NFKB1", "RELA",
    "YAP1",
    # Metabolism
    "LDHA", "PKM", "HK2", "G6PD", "IDH1",
    # Immune / cytokines
    "IL6", "TNF", "IFNG",
    # Transcription factors
    "SP1", "JUNB", "FOS", "ETS1",
    "SOX2",
    # Apoptosis
    "CASP3", "CASP8", "CASP9",
    # Cytoskeleton / adhesion
    "CDH1", "CDH2", "FN1", "ITGB1",
    "RAC1", "CDC42", "RHOA",
    # Chaperones
    "HSPA4", "HSPA5", "HSPA9", "HSPB1",
    # Ubiquitin / proteasome
    "SKP1", "SKP2", "CUL1",
    # RNA structure / stability
    "YBX1", "ELAVL1", "KHSRP", "STAU1",
    "FMR1",
    # Nuclear transport
    "NPM1", "XPO1",
    # HeLa-enriched / broadly expressed
    "CALM1", "CALM2",
    "S100A4", "S100A6",
    "KRT18", "KRT8",
    "CFL1",
    "LIN28A",
    # EMT markers
    "SNAI1", "SNAI2", "TWIST1", "ZEB1",
    # DNA repair
    "MLH1", "MSH2", "ERCC1",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_background_transcriptome(
    config: OrcSonarConfig,
    exclude_gene: str | None = None,
) -> tuple[list[TranscriptInfo], dict[str, str]]:
    """Return canonical mRNA sequences for the background human transcriptome.

    Queries Ensembl for all genes in _BACKGROUND_GENES (excluding ``exclude_gene``
    to prevent the target gene's own transcripts from appearing as off-targets).

    Results are cached in SQLite (TTL 1 week).  On cache-warm runs this returns
    in under one second.  On a cold cache, expect ~10-20 seconds for ~250 genes.

    Args:
        config: Pipeline config (Ensembl URL + cache path).
        exclude_gene: HGNC symbol to skip (typically the saRNA target gene).

    Returns:
        Tuple of (list[TranscriptInfo], dict[transcript_id → mRNA sequence]).
        Both containers have the same set of transcript IDs.
        Returns empty containers on complete API failure (graceful degradation).
    """
    exclude_upper = exclude_gene.upper() if exclude_gene else ""
    genes = [g for g in _BACKGROUND_GENES if g.upper() != exclude_upper]

    canonical = _load_canonical_transcripts(genes, config)
    if not canonical:
        logger.warning("transcriptome_fetcher: no canonical transcripts resolved — returning empty")
        return [], {}

    transcript_infos = list(canonical.values())
    sequences = _load_sequences([t.transcript_id for t in transcript_infos], config)

    # Keep only transcripts for which we actually have a sequence
    transcript_infos = [t for t in transcript_infos if t.transcript_id in sequences]

    logger.info(
        f"transcriptome_fetcher: {len(transcript_infos)} background transcripts ready "
        f"(excluded: {exclude_gene or 'none'})"
    )
    return transcript_infos, sequences


# ---------------------------------------------------------------------------
# Transcript resolution
# ---------------------------------------------------------------------------


def _load_canonical_transcripts(
    genes: list[str],
    config: OrcSonarConfig,
) -> dict[str, TranscriptInfo]:
    """Resolve canonical transcript for each gene symbol, using cache.

    Args:
        genes: List of HGNC gene symbols.
        config: OrcSonarConfig.

    Returns:
        Mapping gene_symbol → TranscriptInfo for successfully resolved genes.
    """
    canonical: dict[str, TranscriptInfo] = {}
    uncached: list[str] = []

    with Cache(config.data_paths.cache_db) as cache:
        for gene in genes:
            key = f"bg:canonical:{gene.upper()}"
            val = cache.get(key)
            if val is not None:
                try:
                    canonical[gene] = TranscriptInfo(**val)
                except Exception as exc:
                    logger.debug(f"transcriptome_fetcher: bad cache entry for {gene}: {exc}")
                    uncached.append(gene)
            else:
                uncached.append(gene)

    logger.info(
        f"transcriptome_fetcher: {len(canonical)} genes from cache, "
        f"{len(uncached)} to fetch from Ensembl"
    )

    if not uncached:
        return canonical

    # Fetch missing genes in batches and write back to cache
    fetched = _batch_lookup_symbols(uncached, config)
    with Cache(config.data_paths.cache_db) as cache:
        for gene, t_info in fetched.items():
            cache.set(f"bg:canonical:{gene.upper()}", t_info.model_dump(), ttl_hours=168)
            canonical[gene] = t_info

    return canonical


def _batch_lookup_symbols(
    genes: list[str],
    config: OrcSonarConfig,
) -> dict[str, TranscriptInfo]:
    """POST /lookup/symbol/homo_sapiens for up to _LOOKUP_BATCH genes at once.

    Args:
        genes: HGNC gene symbols to look up.
        config: OrcSonarConfig.

    Returns:
        Mapping gene_symbol → TranscriptInfo (canonical transcript only).
        Genes with no Ensembl entry are silently omitted.
    """
    result: dict[str, TranscriptInfo] = {}
    url = f"{config.ensembl_base_url}/lookup/symbol/homo_sapiens"

    for batch in _batches(genes, _LOOKUP_BATCH):
        try:
            data: dict = _ensembl_post(url, {"symbols": batch, "expand": 1})
            time.sleep(_ENSEMBL_DELAY)
        except Exception as exc:
            logger.warning(f"transcriptome_fetcher: symbol lookup failed for batch of {len(batch)}: {exc}")
            continue

        for symbol, gene_data in data.items():
            if not isinstance(gene_data, dict):
                continue
            transcripts_raw: list[dict] = gene_data.get("Transcript", [])
            if not transcripts_raw:
                continue

            canonical_raw = next(
                (t for t in transcripts_raw if t.get("is_canonical") == 1),
                transcripts_raw[0],
            )

            chrom: str = gene_data.get("seq_region_name", "")
            if chrom and not chrom.startswith("chr"):
                chrom = f"chr{chrom}"

            strand_int: int = canonical_raw.get("strand", gene_data.get("strand", 1))
            strand = "+" if strand_int == 1 else "-"

            try:
                result[symbol] = TranscriptInfo(
                    transcript_id=canonical_raw["id"],
                    gene=symbol.upper(),
                    chrom=chrom,
                    start=canonical_raw.get("start", gene_data.get("start", 0)),
                    end=canonical_raw.get("end", gene_data.get("end", 0)),
                    strand=strand,
                    is_canonical=True,
                    source="Ensembl",
                )
            except Exception as exc:
                logger.debug(f"transcriptome_fetcher: could not build TranscriptInfo for {symbol}: {exc}")

    return result


# ---------------------------------------------------------------------------
# Sequence fetching
# ---------------------------------------------------------------------------


def _load_sequences(
    transcript_ids: list[str],
    config: OrcSonarConfig,
) -> dict[str, str]:
    """Return mRNA sequences for transcript IDs, fetching uncached ones in batches.

    Sequence cache key ``seq:{transcript_id}`` is shared with transcript_resolver.

    Args:
        transcript_ids: Ensembl ENST accessions.
        config: OrcSonarConfig.

    Returns:
        Mapping transcript_id → uppercase mRNA sequence (RNA U or DNA T — mixed OK,
        caller normalises to U).
    """
    sequences: dict[str, str] = {}
    uncached: list[str] = []

    with Cache(config.data_paths.cache_db) as cache:
        for tid in transcript_ids:
            val = cache.get(f"seq:{tid}")
            if val is not None:
                seq = val.get("sequence", "")
                if seq:
                    sequences[tid] = seq
                else:
                    uncached.append(tid)
            else:
                uncached.append(tid)

    if not uncached:
        return sequences

    logger.info(f"transcriptome_fetcher: fetching {len(uncached)} sequences from Ensembl")
    fetched = _batch_fetch_sequences(uncached, config)

    with Cache(config.data_paths.cache_db) as cache:
        for tid, seq in fetched.items():
            cache.set(f"seq:{tid}", {"sequence": seq}, ttl_hours=168)
            sequences[tid] = seq

    return sequences


def _batch_fetch_sequences(
    transcript_ids: list[str],
    config: OrcSonarConfig,
) -> dict[str, str]:
    """POST /sequence/id to Ensembl for up to _SEQ_BATCH IDs per request.

    Args:
        transcript_ids: List of ENST accessions.
        config: OrcSonarConfig.

    Returns:
        Mapping transcript_id → uppercase mRNA sequence.
    """
    result: dict[str, str] = {}
    url = f"{config.ensembl_base_url}/sequence/id"

    for batch in _batches(transcript_ids, _SEQ_BATCH):
        try:
            data: list[dict] = _ensembl_post(url, {"ids": batch, "type": "cdna"})
            time.sleep(_ENSEMBL_DELAY)
        except Exception as exc:
            logger.warning(
                f"transcriptome_fetcher: sequence batch fetch failed for {len(batch)} IDs: {exc}"
            )
            continue

        if not isinstance(data, list):
            logger.warning(f"transcriptome_fetcher: unexpected /sequence/id response type: {type(data)}")
            continue

        for item in data:
            if not isinstance(item, dict):
                continue
            tid = item.get("id", "")
            seq = item.get("seq", "")
            if tid and seq:
                result[tid] = seq.upper()

    return result


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ensembl_post(url: str, payload: dict) -> dict | list:  # type: ignore[type-arg]
    """POST to Ensembl REST; tenacity retries on network/HTTP errors.

    Args:
        url: Ensembl REST endpoint URL.
        payload: JSON-serialisable request body.

    Returns:
        Parsed JSON response (dict or list).

    Raises:
        requests.RequestException: After retries exhausted.
    """
    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _batches(items: list, size: int) -> Iterator[list]:
    """Yield successive fixed-size chunks from items.

    Args:
        items: Input list.
        size: Maximum batch size.

    Yields:
        Sublists of length ≤ size.
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]
