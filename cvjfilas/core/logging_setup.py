from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(base_dir: Path, filename: str = "cvj_trace.log") -> logging.Logger:
    """Cria logger que escreve em arquivo + console e captura exceções não tratadas."""
    trace_path = base_dir / filename

    logger = logging.getLogger("CVJFILAS")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if not any(
        isinstance(h, RotatingFileHandler)
        and getattr(h, "baseFilename", "").lower().endswith(filename.lower())
        for h in logger.handlers
    ):
        fh = RotatingFileHandler(
            trace_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    def _excepthook(exc_type, exc, tb):
        logger.exception("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = _excepthook
    return logger
