"""Helper functions: logging setup and text normalization."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Serbian diacritics -> plain latin.
_DIACRITICS = {
    "č": "c",
    "ć": "c",
    "š": "s",
    "ž": "z",
    "đ": "dj",
}

_WS_RE = re.compile(r"\s+")


_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO, log_file: Path | None = None
) -> logging.Logger:
    """Configure console logging (and optional rotating file logs).

    A long-running bot benefits from a durable log; when ``log_file`` is given,
    a 1 MB-rotating handler (5 backups) is attached alongside the console.
    """
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    root = logging.getLogger()
    root.setLevel(level)

    # Idempotent: clear our own handlers so repeated calls don't duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return logging.getLogger("polovni_monitor")


def normalize_text(text: str) -> str:
    """lowercase + strip Serbian diacritics + collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = "".join(_DIACRITICS.get(ch, ch) for ch in text)
    return _WS_RE.sub(" ", text).strip()
