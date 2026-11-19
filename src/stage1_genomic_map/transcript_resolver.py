"""Transcript isoform resolver for orcSONAR Stage 1.

Priority: Ensembl REST API → NCBI RefSeq fallback.
All API results are cached in SQLite (TTL = 1 week).
"""

from __future__ import annotations

import time
from typing import Any

import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.cache import Cache
from src.core.config import OrcSonarConfig, config_from_mapping
from src.core.exceptions import DataSourceError
from src.core.models import TranscriptInfo

# Inter-request delays to respect API rate limits
_ENSEMBL_DELAY = 1 / 15  # 15 req/s
_NCBI_DELAY = 1 / 3      # 3 req/s (10/s with API key, conservative without)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_transcripts(gene_name: str, config: OrcSonarConfig) -> list[TranscriptInfo]:
    """Fetch all transcript isoforms for a gene.

    Tries Ensembl first; falls back to NCBI RefSeq when Ensembl is
    unavailable or returns no transcripts.

    Args:
        gene_name: HGNC gene symbol (e.g. "VEGFA").
        config: OrcSonarConfig with API URLs and cache path.

    Returns:
        Non-empty list of TranscriptInfo; exactly one entry has
        ``is_canonical=True``.

    Raises:
        DataSourceError: If no transcripts are found in either source.
    """
    transcripts = _query_ensembl(gene_name, config)
    if transcripts:
        return transcripts

    logger.warning(f"'{gene_name}' not found in Ensembl — falling back to RefSeq")
    transcripts = _query_refseq_fallback(gene_name, config)
    if transcripts:
        return transcripts

    raise DataSourceError(
        f"No transcripts found for '{gene_name}' in Ensembl or RefSeq"
    )


def get_transcript_sequence(transcript_id: str, config: OrcSonarConfig) -> str:
    """Fetch the mRNA sequence for a transcript ID.

    Dispatches to Ensembl (ENST…) or NCBI (NM_…) based on the ID prefix.
    Results are cached in SQLite.

    Args:
        transcript_id: Transcript accession ("ENST…" or "NM_…").
        config: OrcSonarConfig.

    Returns:
        Upper-case mRNA sequence string.

    Raises:
        DataSourceError: If the sequence cannot be retrieved.
    """
    cache_key = f"seq:{transcript_id}"
    cache = Cache(config.data_paths.cache_db)

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached["sequence"]

        if transcript_id.startswith("ENST"):
            seq = _fetch_ensembl_sequence(transcript_id, config)
        else:
            seq = _fetch_refseq_sequence(transcript_id, config)

        cache.set(cache_key, {"sequence": seq}, ttl_hours=168)
        return seq
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Ensembl
# ---------------------------------------------------------------------------


def _query_ensembl(gene_name: str, config: OrcSonarConfig) -> list[TranscriptInfo]:
    """Fetch all transcripts from Ensembl REST API.

    Endpoint: ``GET /lookup/symbol/homo_sapiens/{gene}?expand=1``

    When no transcript has ``is_canonical=1``, the longest transcript
    (by genomic span) is promoted to canonical.

    Args:
        gene_name: HGNC gene symbol.
        config: Config with ``ensembl_base_url`` and ``data_paths.cache_db``.

    Returns:
        List of TranscriptInfo (empty list on any failure).
    """
    cache_key = f"ensembl:transcripts:{gene_name.upper()}"
    cache = Cache(config.data_paths.cache_db)

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Ensembl transcript cache hit: {gene_name}")
            return [TranscriptInfo(**t) for t in cached["transcripts"]]

        url = (
            f"{config.ensembl_base_url}/lookup/symbol/homo_sapiens/{gene_name}"
            "?expand=1&content-type=application/json"
        )

        try:
            data = _ensembl_get(url)
            time.sleep(_ENSEMBL_DELAY)
        except requests.RequestException as exc:
            logger.warning(f"Ensembl transcript lookup failed for '{gene_name}': {exc}")
            return []

        raw = data.get("Transcript", [])
        if not raw:
            logger.warning(f"Ensembl returned no transcripts for '{gene_name}'")
            return []

        chrom: str = data.get("seq_region_name", "")
        if not chrom.startswith("chr"):
            chrom = f"chr{chrom}"

        gene_strand_int: int = data.get("strand", 1)

        any_canonical = any(t.get("is_canonical", 0) == 1 for t in raw)

        transcripts: list[TranscriptInfo] = []
        for t in raw:
            t_strand_int: int = t.get("strand", gene_strand_int)
            t_strand = "+" if t_strand_int == 1 else "-"
            transcripts.append(
                TranscriptInfo(
                    transcript_id=t["id"],
                    gene=gene_name.upper(),
                    chrom=chrom,
                    start=t.get("start", data.get("start", 0)),
                    end=t.get("end", data.get("end", 0)),
                    strand=t_strand,
                    is_canonical=bool(t.get("is_canonical", 0)),
                    source="Ensembl",
                )
            )

        # If Ensembl flagged no canonical, promote the longest transcript
        if not any_canonical and transcripts:
            longest_idx = max(
                range(len(transcripts)),
                key=lambda i: transcripts[i].end - transcripts[i].start,
            )
            transcripts[longest_idx] = transcripts[longest_idx].model_copy(
                update={"is_canonical": True}
            )

        cache.set(
            cache_key,
            {"transcripts": [t.model_dump() for t in transcripts]},
            ttl_hours=168,
        )
        return transcripts

    finally:
        cache.close()


def _fetch_ensembl_sequence(transcript_id: str, config: OrcSonarConfig) -> str:
    """Fetch mRNA sequence from Ensembl for an ENST transcript.

    Args:
        transcript_id: ENST accession.
        config: Config with ``ensembl_base_url``.

    Returns:
        Upper-case mRNA sequence.

    Raises:
        DataSourceError: On API failure or empty response.
    """
    url = (
        f"{config.ensembl_base_url}/sequence/id/{transcript_id}"
        "?type=cdna&content-type=application/json"
    )
    try:
        data = _ensembl_get(url)
        time.sleep(_ENSEMBL_DELAY)
    except requests.RequestException as exc:
        raise DataSourceError(
            f"Ensembl sequence fetch failed for '{transcript_id}': {exc}"
        ) from exc

    seq: str = data.get("seq", "")
    if not seq:
        raise DataSourceError(
            f"Ensembl returned empty sequence for '{transcript_id}'"
        )
    return seq.upper()


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ensembl_get(url: str) -> dict:
    """GET to Ensembl REST; tenacity retries on network/HTTP errors."""
    resp = requests.get(
        url, headers={"Content-Type": "application/json"}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# RefSeq fallback
# ---------------------------------------------------------------------------


def _query_refseq_fallback(
    gene_name: str, config: OrcSonarConfig
) -> list[TranscriptInfo]:
    """Fetch transcripts from NCBI RefSeq.

    Steps:
      1. ``esearch db=gene`` → NCBI gene_id
      2. ``esummary db=gene`` → chromosome + coordinates + strand
      3. ``elink gene → nuccore`` → NM_ accession UIDs
      4. ``esummary db=nuccore`` → accession strings

    The first accession (MANE Select / NM_ reference) is marked canonical.

    Args:
        gene_name: HGNC gene symbol.
        config: Config with ``ncbi_eutils_url`` and ``data_paths.cache_db``.

    Returns:
        List of TranscriptInfo (empty list on any failure).
    """
    cache_key = f"refseq:transcripts:{gene_name.upper()}"
    cache = Cache(config.data_paths.cache_db)

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"RefSeq transcript cache hit: {gene_name}")
            return [TranscriptInfo(**t) for t in cached["transcripts"]]

        gene_id = _ncbi_esearch_gene_id(gene_name, config)
        if gene_id is None:
            return []

        gene_info = _ncbi_gene_summary(gene_id, config)
        if gene_info is None:
            return []

        accessions = _ncbi_refseq_mrna_accessions(gene_id, config)
        if not accessions:
            logger.warning(f"No RefSeq mRNA accessions for '{gene_name}' (gene_id={gene_id})")
            return []

        transcripts = [
            TranscriptInfo(
                transcript_id=acc,
                gene=gene_name.upper(),
                chrom=gene_info["chrom"],
                start=gene_info["start"],
                end=gene_info["end"],
                strand=gene_info["strand"],
                is_canonical=(i == 0),
                source="RefSeq",
            )
            for i, acc in enumerate(accessions)
        ]

        cache.set(
            cache_key,
            {"transcripts": [t.model_dump() for t in transcripts]},
            ttl_hours=168,
        )
        return transcripts

    finally:
        cache.close()


def _ncbi_esearch_gene_id(
    gene_name: str, config: OrcSonarConfig
) -> str | None:
    """Return the NCBI Gene UID for a human gene symbol.

    Args:
        gene_name: Gene symbol.
        config: Config with ``ncbi_eutils_url``.

    Returns:
        Gene UID string, or None on failure / not found.
    """
    url = (
        f"{config.ncbi_eutils_url}esearch.fcgi"
        f"?db=gene&term={gene_name}[Gene+Name]+AND+Homo+sapiens[Organism]"
        "&retmode=json&retmax=1"
    )
    try:
        data = _ncbi_get(url)
        time.sleep(_NCBI_DELAY)
        ids: list[str] = data.get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
    except requests.RequestException as exc:
        logger.warning(f"NCBI esearch failed for '{gene_name}': {exc}")
        return None


def _ncbi_gene_summary(
    gene_id: str, config: OrcSonarConfig
) -> dict | None:
    """Return genomic position dict from NCBI Gene esummary.

    Returns a dict with keys ``chrom``, ``start``, ``end``, ``strand``,
    or None on failure.

    Args:
        gene_id: NCBI Gene UID.
        config: Config with ``ncbi_eutils_url``.
    """
    url = (
        f"{config.ncbi_eutils_url}esummary.fcgi"
        f"?db=gene&id={gene_id}&retmode=json"
    )
    try:
        data = _ncbi_get(url)
        time.sleep(_NCBI_DELAY)
        gene_rec = data.get("result", {}).get(gene_id, {})
        genomicinfo: list[dict] = gene_rec.get("genomicinfo", [])
        if not genomicinfo:
            logger.warning(f"NCBI gene summary missing genomicinfo for gene_id={gene_id}")
            return None

        gi = genomicinfo[0]
        chrom_raw: str = gi.get("chrloc", "") or gene_rec.get("chromosome", "")
        chrom = f"chr{chrom_raw}" if not chrom_raw.startswith("chr") else chrom_raw

        chrstart: int = gi.get("chrstart", 0)
        chrstop: int = gi.get("chrstop", 0)

        # NCBI uses chrstart > chrstop to indicate minus-strand genes
        if chrstart <= chrstop:
            return {"chrom": chrom, "start": chrstart, "end": chrstop, "strand": "+"}
        return {"chrom": chrom, "start": chrstop, "end": chrstart, "strand": "-"}

    except requests.RequestException as exc:
        logger.warning(f"NCBI esummary failed for gene_id={gene_id}: {exc}")
        return None


def _ncbi_refseq_mrna_accessions(
    gene_id: str, config: OrcSonarConfig
) -> list[str]:
    """Return RefSeq mRNA accessions (NM_…) linked to an NCBI gene ID.

    Uses ``elink gene → nuccore_refseqrna`` followed by
    ``esummary db=nuccore`` to resolve UIDs to accession strings.

    Args:
        gene_id: NCBI Gene UID.
        config: Config with ``ncbi_eutils_url``.

    Returns:
        Sorted list of NM_ accession strings (up to 20).
    """
    link_url = (
        f"{config.ncbi_eutils_url}elink.fcgi"
        f"?dbfrom=gene&db=nuccore&id={gene_id}"
        "&linkname=gene_nuccore_refseqrna&retmode=json"
    )
    try:
        link_data = _ncbi_get(link_url)
        time.sleep(_NCBI_DELAY)

        linksets: list[dict] = link_data.get("linksets", [])
        if not linksets:
            return []
        linksetdbs: list[dict] = linksets[0].get("linksetdbs", [])
        if not linksetdbs:
            return []
        nuccore_ids: list[str] = [str(i) for i in linksetdbs[0].get("links", [])]
        if not nuccore_ids:
            return []

        nuccore_ids = nuccore_ids[:20]
        id_str = ",".join(nuccore_ids)

        summary_url = (
            f"{config.ncbi_eutils_url}esummary.fcgi"
            f"?db=nuccore&id={id_str}&retmode=json"
        )
        summary_data = _ncbi_get(summary_url)
        time.sleep(_NCBI_DELAY)

        result: dict = summary_data.get("result", {})
        return [
            result[uid]["accessionversion"]
            for uid in result.get("uids", [])
            if result.get(uid, {}).get("accessionversion", "").startswith("NM_")
        ]

    except requests.RequestException as exc:
        logger.warning(f"NCBI elink/esummary failed for gene_id={gene_id}: {exc}")
        return []


def _fetch_refseq_sequence(accession: str, config: OrcSonarConfig) -> str:
    """Fetch mRNA FASTA from NCBI for an NM_ accession.

    Args:
        accession: RefSeq mRNA accession (NM_…).
        config: Config with ``ncbi_eutils_url``.

    Returns:
        Upper-case mRNA sequence string.

    Raises:
        DataSourceError: On API failure or empty FASTA.
    """
    url = (
        f"{config.ncbi_eutils_url}efetch.fcgi"
        f"?db=nuccore&id={accession}&rettype=fasta&retmode=text"
    )
    try:
        text = _ncbi_get_text(url)
        time.sleep(_NCBI_DELAY)
    except requests.RequestException as exc:
        raise DataSourceError(
            f"RefSeq sequence fetch failed for '{accession}': {exc}"
        ) from exc

    seq = "".join(
        line.strip() for line in text.splitlines() if line and not line.startswith(">")
    )
    if not seq:
        raise DataSourceError(f"RefSeq returned empty FASTA for '{accession}'")
    return seq.upper()


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ncbi_get(url: str) -> dict:
    """GET to NCBI E-utilities returning JSON; tenacity retries on errors."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _ncbi_get_text(url: str) -> str:
    """GET to NCBI E-utilities returning plain text; tenacity retries on errors."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Snakemake run() entry point
# ---------------------------------------------------------------------------


def run(
    gene: str,
    ensembl_url: str,
    ncbi_url: str,
    output_path: str,
    log_path: str,
    config_raw: dict[str, Any] | None = None,
) -> None:
    """Resolve transcripts for *gene* and write stage1_transcripts.json."""
    import json
    import sys
    from pathlib import Path as _Path

    _Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(log_path, level="DEBUG")
    logger.add(sys.stderr, level="INFO")

    config = config_from_mapping(config_raw, 
        target_gene=gene,
        ensembl_base_url=ensembl_url,
        ncbi_eutils_url=ncbi_url,
    )

    try:
        transcripts = resolve_transcripts(gene, config)
        payload = {
            "gene": gene,
            "transcripts": [t.model_dump() for t in transcripts],
            "count": len(transcripts),
        }
        logger.info(f"transcript_resolver: {gene} → {len(transcripts)} transcript(s)")
    except Exception as exc:
        # An empty transcript list is not "this gene has no transcripts"; it
        # silently removes the target gene from the scan and leaves only the
        # background set, so the run answers a different question without
        # saying so (audit 2026-11-19, the Bulgu 12 shape one stage earlier).
        raise DataSourceError(
            f"transcript_resolver: could not resolve any transcript for "
            f"'{gene}': {exc}. Writing an empty list would drop the target "
            f"gene from the scan without saying so."
        ) from exc

    out = _Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
