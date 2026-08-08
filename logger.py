"""File logging for debugging runs (the Rich Live dashboard hides stdout)."""
from __future__ import annotations

import logging
from pathlib import Path

_LOG_NAME = "farm"


def setup_logger(output_dir: str = "output", level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(_LOG_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    log_dir = Path(output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_dir / "farm.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(message)s")
    )
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOG_NAME)
