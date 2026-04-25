"""Multi-domain score integrator and cell-specific risk modulator (Stage 7).

Architecture
------------
Final Risk = Base_Score × Cell_Modifier   (clamped to [0, 1])

Base_Score  — weighted sum of all five domain scores using configurable weights
              (default weights from config/config.yaml sum exactly to 1.0).

Cell_Modifier — derived from cell-dependent activity signals (chromatin
              accessibility, gene expression, execution context).  A locus
              with closed chromatin and absent expression cannot be
              transcriptionally active → modifier shrinks risk below the
              cell-agnostic baseline.  An open, highly expressed locus
              amplifies risk above baseline.

Modifier range: [0.3, 1.7]  (neutral at cell_activity = 0.5 → modifier 1.0)
"""

from __future__ import annotations

import math

from loguru import logger

from src.core.config import RiskThresholds, ScoringWeights
from src.core.models import DomainScores
from src.scoring.classifier import RiskClass, classify

_VALID_WEIGHT_KEYS: frozenset[str] = frozenset(
    {
        "sequence_specificity",
        "variant_toxicity",
        "epigenetic_context",
        "biophysics_structure",
        "execution_safety",
    }
)


def _validate_weights(weights: dict[str, float]) -> None:
    """Raise ``ValueError`` if *weights* have invalid keys or do not sum to 1.

    Args:
        weights: Domain weight mapping.

    Raises:
        ValueError: On invalid keys or weights not summing to 1.0 (± 1e-6).
    """
    invalid = set(weights.keys()) - _VALID_WEIGHT_KEYS
    if invalid:
        raise ValueError(
            f"Invalid weight keys: {sorted(invalid)}. "
            f"Allowed: {sorted(_VALID_WEIGHT_KEYS)}"
        )
    total = sum(weights.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(
            f"Weights must sum to 1.0, got {total:.8f} "
            f"(difference: {abs(total - 1.0):.2e})"
        )


class ScoreIntegrator:
    """Integrates domain scores and applies the cell-specific risk modifier.

    Args:
        risk_thresholds: Risk classification thresholds.  Uses project
            defaults (safe=0.3, warning=0.6, high_risk=0.8) when ``None``.
    """

    def __init__(
        self,
        risk_thresholds: RiskThresholds | None = None,
    ) -> None:
        self._thresholds = risk_thresholds or RiskThresholds()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def integrate(
        self,
        domain_scores: DomainScores,
        weights: dict[str, float],
    ) -> float:
        """Compute the weighted sum of all five domain scores.

        Args:
            domain_scores: Normalised scores for each domain (each in [0, 1]).
            weights: Mapping of domain name → weight.  Keys must be a subset
                of ``_VALID_WEIGHT_KEYS`` and values must sum to 1.0.

        Returns:
            Integrated risk score in [0, 1].

        Raises:
            ValueError: If weights are invalid or do not sum to 1.0.
        """
        _validate_weights(weights)

        score = (
            domain_scores.sequence_specificity
            * weights.get("sequence_specificity", 0.0)
            + domain_scores.variant_toxicity
            * weights.get("variant_toxicity", 0.0)
            + domain_scores.epigenetic_context
            * weights.get("epigenetic_context", 0.0)
            + domain_scores.biophysics_structure
            * weights.get("biophysics_structure", 0.0)
            + domain_scores.execution_safety
            * weights.get("execution_safety", 0.0)
        )
        result = max(0.0, min(1.0, score))

        logger.debug(
            f"integrate: seq={domain_scores.sequence_specificity:.3f} "
            f"var={domain_scores.variant_toxicity:.3f} "
            f"epi={domain_scores.epigenetic_context:.3f} "
            f"bio={domain_scores.biophysics_structure:.3f} "
            f"exec={domain_scores.execution_safety:.3f} → {result:.4f}"
        )
        return result

    def apply_cell_modifier(
        self,
        base_score: float,
        epigenetic_context: dict[str, float],
    ) -> float:
        """Scale *base_score* by a cell-specific activity modifier.

        The modifier is a linear function of a combined cell-activity signal:

            cell_activity = 0.4 × atac + 0.4 × expression + 0.2 × execution
            modifier      = 0.3 + 1.4 × cell_activity        (range [0.3, 1.7])
            final_score   = clamp(base_score × modifier, 0, 1)

        Neutral point: cell_activity = 0.5 → modifier = 1.0 (no change).

        Args:
            base_score: Cell-independent base risk in [0, 1].
            epigenetic_context: Dict with optional float keys:

                - ``atac_score``       — chromatin accessibility in [0, 1]
                - ``expression_score`` — gene expression level in [0, 1]
                - ``execution_score``  — execution safety context in [0, 1]

                Missing keys default to 0.5 (neutral).

        Returns:
            Final risk score in [0, 1].
        """
        atac = max(0.0, min(1.0, epigenetic_context.get("atac_score", 0.5)))
        expr = max(0.0, min(1.0, epigenetic_context.get("expression_score", 0.5)))
        exec_ = max(0.0, min(1.0, epigenetic_context.get("execution_score", 0.5)))

        cell_activity = 0.40 * atac + 0.40 * expr + 0.20 * exec_
        modifier = 0.30 + 1.40 * cell_activity

        final = max(0.0, min(1.0, base_score * modifier))

        logger.debug(
            f"cell_modifier: atac={atac:.3f} expr={expr:.3f} exec={exec_:.3f} "
            f"activity={cell_activity:.3f} modifier={modifier:.3f} "
            f"base={base_score:.4f} → {final:.4f}"
        )
        return final

    def classify_risk(self, final_score: float) -> RiskClass:
        """Classify a final risk score into a ``RiskClass``.

        Args:
            final_score: Integrated (and optionally cell-modified) risk in [0, 1].

        Returns:
            ``RiskClass`` enum value.
        """
        return classify(final_score, self._thresholds)

    # ------------------------------------------------------------------
    # Convenience: run the full pipeline in one call
    # ------------------------------------------------------------------

    def score(
        self,
        domain_scores: DomainScores,
        epigenetic_context: dict[str, float],
        weights: dict[str, float] | None = None,
    ) -> tuple[float, RiskClass]:
        """Run integrate → apply_cell_modifier → classify_risk in sequence.

        Args:
            domain_scores: Normalised scores for all five domains.
            epigenetic_context: Cell-activity context dict (see
                ``apply_cell_modifier`` for key definitions).
            weights: Domain weights summing to 1.0.  Defaults to
                ``ScoringWeights`` from config when ``None``.

        Returns:
            Tuple of ``(final_score, risk_class)``.
        """
        if weights is None:
            sw = ScoringWeights()
            weights = {
                "sequence_specificity": sw.sequence_specificity,
                "variant_toxicity": sw.variant_toxicity,
                "epigenetic_context": sw.epigenetic_context,
                "biophysics_structure": sw.biophysics_structure,
                "execution_safety": sw.execution_safety,
            }

        base = self.integrate(domain_scores, weights)
        final = self.apply_cell_modifier(base, epigenetic_context)
        risk = self.classify_risk(final)

        logger.info(
            f"scoring: base={base:.4f} final={final:.4f} risk={risk.value}"
        )
        return final, risk
