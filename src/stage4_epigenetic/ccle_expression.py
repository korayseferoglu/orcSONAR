"""CCLE gene expression reader for Stage 4.

Reads log₂(TPM+1) expression values from the CCLE_Expression.csv matrix
(291 MB, ~1 719 cell lines × 19 215 genes) using lazy column selection so
only the requested gene column is parsed into memory on each call.

Expression semantics:
  A gene that is highly expressed in the target cell line is more likely to
  be transcriptionally active → an off-target site within its regulatory
  region poses elevated engagement risk.  A gene with zero or very low
  expression is unlikely to be affected → risk decreases.

  expression_value (log₂(TPM+1)):
    0.0 → not detected
    > 1.0 (is_expressed=True) → approximately ≥ 1 TPM, detectable
    > 5.0 → high expression
    > 8.0 → very high expression

  expression_percentile: rank of this cell line among all CCLE lines for
  the given gene.  High percentile (> 0.75) means the gene is unusually
  active in this cell line.

Implementation notes:
  - Header is read once on first call (nrows=0) → O(columns) only.
  - Per gene: pandas reads the full CSV but parses only 3 columns
    (ModelID, IsDefaultEntryForModel, gene_col).  For a 291 MB file with
    19 221 columns this reduces RAM footprint from ~4 GB to ~1 MB.
  - Results are cached in SQLite with a 1-year TTL (CCLE is a static dataset).
  - DepMap ACH IDs are loaded from config/ccle_depmap_ids.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from loguru import logger

from src.core.cache import Cache
from src.core.config import OrcSonarConfig
from src.core.models import CCLEResult

_EXPRESSION_THRESHOLD: float = 1.0   # log2(TPM+1) > 1 ≈ ≥ 1 TPM
_CCLE_TTL_HOURS: int = 8_760         # 1 year — static dataset
_MODEL_ID_COL: str = "ModelID"
_IS_DEFAULT_COL: str = "IsDefaultEntryForModel"
_DEFAULT_DEPMAP_IDS_YAML: str = "config/ccle_depmap_ids.yaml"


class CCLEReader:
    """Reads CCLE gene expression data with lazy column loading.

    Args:
        config: Pipeline configuration (provides CSV path and cache DB path).
        csv_path: Override the CCLE CSV path (default: ``config.data_paths.ccle_csv``).
        depmap_ids_yaml: Path to the cell-line → DepMap ACH-ID mapping YAML.
    """

    def __init__(
        self,
        config: OrcSonarConfig,
        csv_path: str | Path | None = None,
        depmap_ids_yaml: str | Path = _DEFAULT_DEPMAP_IDS_YAML,
    ) -> None:
        self._csv_path = Path(csv_path or config.data_paths.ccle_csv)
        self._cache_db = config.data_paths.cache_db
        self._depmap_ids: dict[str, str] = self._load_depmap_ids(Path(depmap_ids_yaml))
        # Lazily populated on first _ensure_header() call
        self._gene_col_map: dict[str, str] = {}
        self._header_loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_expression(self, gene: str, cell_line: str) -> CCLEResult:
        """Return log₂(TPM+1) expression for a gene in a cell line.

        Measured results are cached in SQLite. An **unknown** result — the
        cell line has no DepMap model, the gene is absent from the CCLE header,
        or the row could not be read — carries ``None`` and is deliberately
        **not cached** (roadmap B19). Caching an unknown is how a transient
        failure becomes a year-long one: `_CCLE_TTL_HOURS` is 8760, and B2
        established the rule after the same mistake in `encode_reader`.

        Args:
            gene: HGNC gene symbol, e.g. ``"VEGFA"``.
            cell_line: Cell line name, e.g. ``"HeLa"``.

        Returns:
            CCLEResult whose fields are ``None`` when nothing was measured.
            ``None`` is not ``0.0``: zero expression means the gene cannot be
            silenced, which lowers risk, and an unmeasured gene must never do
            that (invariant 2).
        """
        cache_key = f"ccle:{gene}:{cell_line}"
        with Cache(self._cache_db) as cache:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"ccle_expression: cache HIT {cache_key}")
                return CCLEResult(**cached)

        result = self._compute_expression(gene, cell_line)

        if result.expression_value is None:
            logger.debug(
                f"ccle_expression: {cell_line}/{gene} UNKNOWN — not cached"
            )
            return result

        with Cache(self._cache_db) as cache:
            cache.set(cache_key, result.model_dump(), ttl_hours=_CCLE_TTL_HOURS)

        logger.debug(
            f"ccle_expression: {cell_line}/{gene} "
            f"val={result.expression_value:.4f} "
            f"pct={result.expression_percentile:.3f} "
            f"expressed={result.is_expressed}"
        )
        return result

    def _find_gene_column(self, gene_name: str) -> str | None:
        """Return the full CSV column name for a gene, or None if not found.

        Args:
            gene_name: HGNC gene symbol (e.g. ``"VEGFA"``).

        Returns:
            Full column name like ``"VEGFA (7422)"``, or ``None``.
        """
        self._ensure_header()
        return self._gene_col_map.get(gene_name)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _compute_expression(self, gene: str, cell_line: str) -> CCLEResult:
        # Not "neutral" — *unknown*. There is no neutral expression value: 0.0
        # reads as "not expressed", so it reads as "cannot be silenced", so it
        # lowers risk for a gene nobody looked up (roadmap B19, invariant 2).
        # The name mattered: `_NEUTRAL_SIGNAL = 0.0` is how the same mistake
        # survived six modules in `encode_reader` (B2).
        unknown = CCLEResult(gene=gene, cell_line=cell_line)

        ach_id = self._depmap_ids.get(cell_line)
        if not ach_id:
            logger.warning(
                f"ccle_expression: '{cell_line}' not in DepMap ID mapping "
                f"(check config/ccle_depmap_ids.yaml) — expression is UNKNOWN, "
                f"not zero"
            )
            return unknown

        col_name = self._find_gene_column(gene)
        if col_name is None:
            logger.warning(f"ccle_expression: gene '{gene}' not found in CCLE header")
            return unknown

        value, percentile = self._load_expression(ach_id, col_name, cell_line)
        if value is None:
            return unknown

        return CCLEResult(
            gene=gene,
            cell_line=cell_line,
            expression_value=value,
            is_expressed=value > _EXPRESSION_THRESHOLD,
            expression_percentile=percentile,
        )

    def _load_expression(
        self, ach_id: str, col_name: str, cell_line: str
    ) -> tuple[float | None, float]:
        """Load one gene column from the CSV; compute value and percentile.

        Reads only the three relevant columns (ModelID, IsDefaultEntryForModel,
        gene_col) so the full-width CSV is never parsed into RAM.

        Args:
            ach_id: DepMap ACH identifier for the cell line.
            col_name: Full gene column name (e.g. ``"VEGFA (7422)"``).
            cell_line: Human-readable cell line name (used only for logging).

        Returns:
            ``(expression_value, percentile)`` or ``(None, 0.5)`` on failure.
        """
        if not self._csv_path.exists():
            logger.error(f"ccle_expression: CSV not found at {self._csv_path}")
            return None, 0.5

        try:
            df = pd.read_csv(
                self._csv_path,
                usecols=[_MODEL_ID_COL, _IS_DEFAULT_COL, col_name],
                dtype={_IS_DEFAULT_COL: str},
            )
        except Exception as exc:
            logger.error(f"ccle_expression: CSV read failed: {exc}")
            return None, 0.5

        # Keep only the canonical (default) entry per cell line
        df_default = df[df[_IS_DEFAULT_COL] == "Yes"]

        target_rows = df_default[df_default[_MODEL_ID_COL] == ach_id]
        if target_rows.empty:
            logger.warning(
                f"ccle_expression: {cell_line} ({ach_id}) not in CCLE default entries"
            )
            return None, 0.5

        value = float(target_rows.iloc[0][col_name])

        all_values = df_default[col_name].dropna().values
        percentile = float((all_values < value).mean()) if len(all_values) > 0 else 0.5

        return value, percentile

    def _ensure_header(self) -> None:
        """Parse only the header row to build the gene-name → column-name map."""
        if self._header_loaded:
            return
        if not self._csv_path.exists():
            logger.error(f"ccle_expression: CSV not found at {self._csv_path}")
            self._header_loaded = True
            return
        try:
            df_head = pd.read_csv(self._csv_path, nrows=0)
        except Exception as exc:
            logger.error(f"ccle_expression: header read failed: {exc}")
            self._header_loaded = True
            return

        for col in df_head.columns:
            if " (" in col and col.endswith(")"):
                gene_name = col.split(" (")[0].strip()
                self._gene_col_map[gene_name] = col

        self._header_loaded = True
        logger.debug(
            f"ccle_expression: indexed {len(self._gene_col_map)} gene columns"
        )

    @staticmethod
    def _load_depmap_ids(yaml_path: Path) -> dict[str, str]:
        """Load cell-line → DepMap ACH ID mapping from YAML.

        Args:
            yaml_path: Path to ``ccle_depmap_ids.yaml``.

        Returns:
            ``{cell_line_name: ach_id}`` (null entries excluded).
        """
        if not yaml_path.exists():
            logger.warning(
                f"ccle_expression: DepMap ID YAML not found at {yaml_path}"
            )
            return {}
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        return {k: v for k, v in raw.items() if v is not None}
