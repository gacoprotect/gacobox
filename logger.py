"""File logging for debugging runs (the Rich Live dashboard hides stdout)."""
from __future__ import annotations

import logging
from contextvars import ContextVar
from pathlib import Path

_LOG_NAME = "farm"

# Every account runs in its own asyncio task, so threadName is always
# MainThread and useless for telling workers apart. A contextvar follows the
# task instead, letting the tag reach provider logs without threading a
# worker id through every call.
_worker: ContextVar[str] = ContextVar("worker", default="--")


def set_worker(worker_id: int | None) -> None:
    _worker.set("--" if worker_id is None else f"W{worker_id + 1}")


class _WorkerFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.worker = _worker.get()
        return True


def setup_logger(output_dir: str = "output", debug: bool = True) -> logging.Logger:
    logger = logging.getLogger(_LOG_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    log_dir = Path(output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_dir / "farm.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(worker)-3s] %(message)s")
    )
    handler.addFilter(_WorkerFilter())
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOG_NAME)
