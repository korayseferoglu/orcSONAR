"""Loguru logging setup — console + rotating daily file."""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: str | Path = "logs", level: str = "DEBUG") -> None:
    """Configure loguru sinks: stderr + daily rotating file.

    Args:
        log_dir: Directory for log files. Created if absent.
        level: Minimum log level (DEBUG / INFO / WARNING / ERROR).
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )

    logger.add(
        log_path / "{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
        encoding="utf-8",
    )
