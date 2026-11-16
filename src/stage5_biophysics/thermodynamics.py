"""Turner nearest-neighbor ΔG calculator for saRNA:mRNA duplexes (Stage 5)."""

from __future__ import annotations

import os

from loguru import logger

from src.core.models import ThermoResult

# Canonical Watson-Crick + GU wobble base pairs (5' strand, 3' strand)
_VALID_PAIRS: frozenset[tuple[str, str]] = frozenset(
    [("A", "U"), ("U", "A"), ("C", "G"), ("G", "C"), ("G", "U"), ("U", "G")]
)

# Terminal AU/GU penalty applies to these pairs
_AU_GU_PAIRS: frozenset[tuple[str, str]] = frozenset(
    [("A", "U"), ("U", "A"), ("G", "U"), ("U", "G")]
)

_NUCS = "ACGU"


def _parse_4x4_tables(
    filepath: str,
) -> dict[tuple[str, str], dict[tuple[str, str], float]]:
    """Parse a Turner .dg file of 4x4 stacking tables.

    Returns:
        Nested dict: starting_pair → {(X, Y): energy}.
        starting_pair = (top_5strand_nuc, bottom_3strand_nuc).
    """
    result: dict[tuple[str, str], dict[tuple[str, str], float]] = {}

    with open(filepath, encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    # Strip comments and blank lines; preserve in order
    clean: list[str] = []
    for line in raw_lines:
        s = line.strip()
        if s and not s.startswith("#"):
            clean.append(s)

    i = 0
    while i < len(clean):
        parts = clean[i].split()

        # Starting pair header: a single 2-char token like "AX", "CX", "GX", "UX"
        if len(parts) == 1 and len(parts[0]) == 2 and parts[0][0] in _NUCS:
            sp_top = parts[0][0]
            i += 1
            if i >= len(clean):
                break

            next_parts = clean[i].split()
            if not (
                len(next_parts) == 1
                and len(next_parts[0]) == 2
                and next_parts[0][0] in _NUCS
            ):
                continue  # unexpected format
            sp_bot = next_parts[0][0]
            i += 1

            # Column header line: "A C G U"
            if i < len(clean) and sorted(clean[i].split()) == sorted(list(_NUCS)):
                i += 1

            # 4 data rows: "A val val val val"
            table: dict[tuple[str, str], float] = {}
            rows_read = 0
            while rows_read < 4 and i < len(clean):
                row_parts = clean[i].split()
                if len(row_parts) == 5 and row_parts[0] in _NUCS:
                    x = row_parts[0]
                    for j, val_str in enumerate(row_parts[1:]):
                        if val_str != ".":
                            y = _NUCS[j]
                            table[(x, y)] = float(val_str)
                    rows_read += 1
                    i += 1
                else:
                    break

            if rows_read == 4:
                result[(sp_top, sp_bot)] = table
        else:
            i += 1

    return result


def _parse_init_energy(filepath: str) -> float:
    """Extract intermolecular initiation free energy from rna.miscloop.dg."""
    marker = "Intermolecular initiation"
    try:
        with open(filepath, encoding="utf-8") as fh:
            lines = fh.readlines()
        for idx, line in enumerate(lines):
            if marker in line:
                for j in range(idx + 1, len(lines)):
                    s = lines[j].strip()
                    if s and not s.startswith("#"):
                        return float(s)
    except (OSError, ValueError) as exc:
        logger.warning("Cannot parse init energy from {}: {}", filepath, exc)
    return 4.1  # Turner 2004 fallback


def _extract_terminal_penalty(
    helix_ends_tables: dict[tuple[str, str], dict[tuple[str, str], float]],
    pair: tuple[str, str],
) -> float:
    """Return terminal end penalty for a given base pair.

    Uses rna.helix_ends.dg tables. Falls back to 0.5 for AU/GU pairs,
    0.0 otherwise, if the table is missing.
    """
    table = helix_ends_tables.get(pair)
    if table:
        # All values in each helix_ends table are equal; return the first.
        return next(iter(table.values()), 0.0)
    # Fallback heuristic
    return 0.5 if pair in _AU_GU_PAIRS else 0.0


class TurnerCalculator:
    """RNA:RNA duplex ΔG calculator using Turner nearest-neighbor parameters.

    Loads parameter files once at construction. Thread-safe for reads.

    Convention:
        sarna  — saRNA sequence, 5'→3'
        target — antiparallel complementary strand, 3'→5' relative to saRNA
                 so that target[i] is paired with sarna[i]

    ΔG(total) = ΔG(init) + Σ ΔG(stack_i) + Σ ΔG(mismatch_penalties)
    """

    _MISMATCH_PENALTY: float = 1.5  # kcal/mol per internal mismatch (simplified)

    def __init__(self, data_dir: str) -> None:
        """Load Turner parameter files from *data_dir*.

        Args:
            data_dir: Path to directory containing rna.stack.dg,
                      rna.helix_ends.dg, rna.miscloop.dg.
        """
        self._stacks: dict[tuple[str, str], dict[tuple[str, str], float]] = {}
        self._helix_ends: dict[tuple[str, str], dict[tuple[str, str], float]] = {}
        self._init_dg: float = 4.1
        self._load(data_dir)

    def _load(self, data_dir: str) -> None:
        stack_path = os.path.join(data_dir, "rna.stack.dg")
        helix_path = os.path.join(data_dir, "rna.helix_ends.dg")
        misc_path = os.path.join(data_dir, "rna.miscloop.dg")

        try:
            self._stacks = _parse_4x4_tables(stack_path)
            logger.debug("Loaded {} stacking tables from {}", len(self._stacks), stack_path)
        except OSError as exc:
            logger.error("Cannot load stack table {}: {}", stack_path, exc)

        try:
            self._helix_ends = _parse_4x4_tables(helix_path)
            logger.debug("Loaded {} helix-end tables from {}", len(self._helix_ends), helix_path)
        except OSError as exc:
            logger.warning("Cannot load helix_ends {}: {}", helix_path, exc)

        self._init_dg = _parse_init_energy(misc_path)
        logger.debug("Initiation ΔG = {} kcal/mol", self._init_dg)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_stack_energy(
        self,
        pair1: tuple[str, str],
        pair2: tuple[str, str],
    ) -> float | None:
        """Look up stacking energy for two consecutive base pairs.

        Args:
            pair1: (5'-strand nuc, 3'-strand nuc) at position i
            pair2: (5'-strand nuc, 3'-strand nuc) at position i+1

        Returns:
            Energy in kcal/mol, or None if the stack is not in the table.
        """
        table = self._stacks.get(pair1)
        if table is None:
            return None
        return table.get(pair2)

    def _get_init_energy(
        self,
        first_pair: tuple[str, str],
        last_pair: tuple[str, str],
    ) -> float:
        """Initiation energy including terminal AU/GU end penalties."""
        init = self._init_dg
        for pair in (first_pair, last_pair):
            init += _extract_terminal_penalty(self._helix_ends, pair)
        return init

    def _get_mismatch_penalty(self, mismatch_type: str = "") -> float:  # noqa: ARG002
        """Simplified internal mismatch penalty."""
        return self._MISMATCH_PENALTY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_duplex_dg(self, sarna: str, target: str) -> ThermoResult:
        """Calculate ΔG for a saRNA:target RNA duplex.

        For perfect-complement duplexes uses the full nearest-neighbor model.
        For duplexes with mismatches: stacks across mismatch boundaries are
        skipped and a flat penalty is added per mismatch position.

        Args:
            sarna:  saRNA sequence 5'→3' (A/C/G/U or T).
            target: Complementary strand 3'→5' relative to saRNA (same index
                    alignment). target[i] is paired with sarna[i].

        Returns:
            ThermoResult with delta_g in kcal/mol.
            More negative delta_g means stronger (potentially off-target) binding.

        Raises:
            ValueError: If sarna and target have different lengths or are empty.
        """
        sarna = sarna.upper().replace("T", "U")
        target = target.upper().replace("T", "U")

        if not sarna:
            raise ValueError("sarna must not be empty")
        if len(sarna) != len(target):
            raise ValueError(
                f"sarna length {len(sarna)} != target length {len(target)}"
            )

        if len(sarna) == 1:
            # Single base pair: only initiation, no stacks
            first_pair = (sarna[0], target[0])
            init = self._get_init_energy(first_pair, first_pair)
            return ThermoResult(delta_g=round(init, 4), stack_energies=[])

        n = len(sarna)
        valid: list[bool] = [
            (sarna[i], target[i]) in _VALID_PAIRS for i in range(n)
        ]

        # ---- Stacking energies -------------------------------------------
        stack_energies: list[float] = []
        for i in range(n - 1):
            if valid[i] and valid[i + 1]:
                pair1 = (sarna[i], target[i])
                pair2 = (sarna[i + 1], target[i + 1])
                energy = self._get_stack_energy(pair1, pair2)
                if energy is None:
                    # Table doesn't have this entry (shouldn't happen for valid pairs)
                    logger.warning(
                        "Stack ({},{}) not found in table; using 0.0", pair1, pair2
                    )
                    energy = 0.0
                stack_energies.append(energy)
            else:
                # At least one of the two positions is a mismatch; no stack
                stack_energies.append(0.0)

        # ---- Mismatch penalties ------------------------------------------
        mismatch_penalties: list[float] = []
        for i in range(n):
            if not valid[i]:
                penalty = self._get_mismatch_penalty(f"{sarna[i]}:{target[i]}")
                mismatch_penalties.append(penalty)

        has_mismatches = bool(mismatch_penalties)

        # ---- Initiation + terminal end penalties -------------------------
        first_pair = (sarna[0], target[0])
        last_pair = (sarna[-1], target[-1])
        init = self._get_init_energy(first_pair, last_pair)

        total_dg = init + sum(stack_energies) + sum(mismatch_penalties)

        return ThermoResult(
            delta_g=round(total_dg, 4),
            stack_energies=stack_energies,
            has_mismatches=has_mismatches,
            mismatch_penalties=mismatch_penalties,
        )
