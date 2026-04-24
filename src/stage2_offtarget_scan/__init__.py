"""Stage 2: Off-target scan — seed-based alignment engine + miRBase overlap."""

from src.stage2_offtarget_scan.mirbase_checker import check_mirbase_overlap
from src.stage2_offtarget_scan.seed_aligner import find_offtargets

__all__ = ["find_offtargets", "check_mirbase_overlap"]
