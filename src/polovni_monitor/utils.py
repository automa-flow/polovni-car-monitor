"""Helper functions: logging setup and text normalization."""
from __future__ import annotations

import logging
import re

# Serbian diacritics -> plain latin.
_DIACRITICS = {
    "č": "c",
    "ć": "c",
    "š": "s",
    "ž": "z",
    "đ": "dj",
}

_WS_RE = re.compile(r"\s+")


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure console logging and return the package logger."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("polovni_monitor")


def normalize_text(text: str) -> str:
    """lowercase + strip Serbian diacritics + collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = "".join(_DIACRITICS.get(ch, ch) for ch in text)
    return _WS_RE.sub(" ", text).strip()
