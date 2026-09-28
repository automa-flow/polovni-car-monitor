"""Listing text analysis and score computation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .utils import normalize_text

# Compiled word-boundary matchers, cached by phrase. Using look-arounds (not
# plain substring) so e.g. the strong term "razvod" does not match inside
# "razvodni", and "lanac" does not match inside an unrelated longer word.
_PHRASE_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _phrase_re(phrase: str) -> re.Pattern[str]:
    pat = _PHRASE_RE_CACHE.get(phrase)
    if pat is None:
        pat = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
        _PHRASE_RE_CACHE[phrase] = pat
    return pat

STRONG_SCORE = 3
WEAK_SCORE = 1
NEGATIVE_SCORE = -5

EXCERPT_RADIUS = 80  # characters around the matched keyword

# Default keywords (used when config/keywords.json is missing).
DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "strong": [
        "lanac", "lanca", "razvodni lanac", "lanac bregaste", "lanac bregastih",
        "zamenjen lanac", "promenjen lanac", "menjan lanac", "urađen lanac",
        "uradjen lanac", "zupčasti kaiš", "zupcasti kais", "kaiš u ulju",
        "kais u ulju", "uljni kaiš", "uljni kais", "set razvoda", "razvod",
        "promenjen kaiš", "zamenjen kaiš", "menjan kaiš",
    ],
    "weak": [
        "veliki servis", "mali i veliki servis", "servisna knjiga",
        "uredno servisiran", "redovno servisiran", "ovlašćeni servis",
        "ovlasceni servis", "servisna istorija",
    ],
    "negative": [
        "nije menjan lanac", "nije zamenjen lanac", "nije menjan kaiš",
        "nije zamenjen kaiš", "čuje se lanac", "cuje se lanac",
        "problem sa lancem", "problem sa kaišem", "potreban servis",
        "treba servis",
    ],
}


@dataclass
class ScoreResult:
    score: int
    positive_hits: list[str] = field(default_factory=list)
    weak_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    excerpt: str = ""


def _normalize_keywords(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Normalize keywords and drop duplicates."""
    result: dict[str, list[str]] = {}
    for bucket in ("strong", "weak", "negative"):
        seen: list[str] = []
        for kw in raw.get(bucket, []):
            norm = normalize_text(kw)
            if norm and norm not in seen:
                seen.append(norm)
        result[bucket] = seen
    return result


_cached_keywords: dict[str, list[str]] | None = None


def load_keywords(path: Path | None = None) -> dict[str, list[str]]:
    """Load keywords from a JSON file, or return the defaults."""
    global _cached_keywords
    if path is not None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _normalize_keywords(raw)
        except (OSError, json.JSONDecodeError):
            return _normalize_keywords(DEFAULT_KEYWORDS)
    if _cached_keywords is None:
        _cached_keywords = _normalize_keywords(DEFAULT_KEYWORDS)
    return _cached_keywords


def _build_excerpt(norm_text: str, hits: list[str]) -> str:
    """A short snippet around the first matched keyword."""
    first = -1
    for kw in hits:
        idx = norm_text.find(kw)
        if idx != -1 and (first == -1 or idx < first):
            first = idx
    if first == -1:
        return norm_text[: EXCERPT_RADIUS * 2].strip()
    start = max(0, first - EXCERPT_RADIUS)
    end = min(len(norm_text), first + EXCERPT_RADIUS)
    snippet = norm_text[start:end].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(norm_text) else ""
    return f"{prefix}{snippet}{suffix}"


def analyze_text(text: str, keywords: dict[str, list[str]] | None = None) -> ScoreResult:
    """Analyze text and return a ScoreResult.

    Each signal type is counted at most once. Negative phrases are removed
    before scanning for strong/weak signals so that a nested strong signal
    (e.g. `menjan lanac` inside `nije menjan lanac`) does not add points.
    """
    kw = keywords or load_keywords()
    norm = normalize_text(text)

    work = norm
    negative_hits: list[str] = []
    for phrase in kw["negative"]:
        if phrase and _phrase_re(phrase).search(work):
            negative_hits.append(phrase)
            work = _phrase_re(phrase).sub(" ", work)

    positive_hits = [p for p in kw["strong"] if p and _phrase_re(p).search(work)]
    weak_hits = [w for w in kw["weak"] if w and _phrase_re(w).search(work)]
    negative_hits = sorted(set(negative_hits))

    score = (
        STRONG_SCORE * len(positive_hits)
        + WEAK_SCORE * len(weak_hits)
        + NEGATIVE_SCORE * len(negative_hits)
    )

    excerpt = _build_excerpt(norm, positive_hits + weak_hits + negative_hits)
    return ScoreResult(
        score=score,
        positive_hits=positive_hits,
        weak_hits=weak_hits,
        negative_hits=negative_hits,
        excerpt=excerpt,
    )
